import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.file import File
from app.models.job_log import JobLog
from app.parsers import get_parser
from app.parsers.pdf_preprocessor import preprocess_pdf
from app.parsers.quality_checker import calculate_quality_score, quality_grade
from app.services.document_service import _compute_file_hash, save_parse_result
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_session_factory() -> async_sessionmaker:
    engine = create_async_engine(settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _parse_file(file_id: str) -> dict:
    session_factory = _get_session_factory()

    async with session_factory() as db:
        result = await db.execute(select(File).where(File.file_id == uuid.UUID(file_id)))
        file = result.scalar_one_or_none()
        if file is None:
            return {"error": f"File not found: {file_id}"}

        # job_log 생성
        job = JobLog(
            file_id=file.file_id,
            job_type="parse",
            status="running",
            started_at=datetime.now(UTC),
        )
        db.add(job)

        file.parse_status = "parsing"
        await db.commit()

        try:
            file_path = Path(file.file_path)

            # PDF 전처리: 고DPI 스캔본은 자동 다운스케일 + 원본 아카이빙
            preprocess_info: dict | None = None
            if file_path.suffix.lower() == ".pdf":
                pp = preprocess_pdf(
                    file_path,
                    settings.documents_originals_root,
                    target_dpi=settings.max_dpi,
                    sample_pages=settings.dpi_sample_pages,
                    jpeg_quality=settings.downscale_jpeg_quality,
                    enabled=settings.auto_downscale_enabled,
                )
                preprocess_info = {
                    "detected_dpi": pp.detected_dpi,
                    "downscaled": pp.downscaled,
                    "original_archive": str(pp.original_archive) if pp.original_archive else None,
                }
                if pp.downscaled:
                    # 작업 파일이 교체되었으므로 hash/size 재계산
                    file.file_hash = _compute_file_hash(file_path)
                    file.file_size = file_path.stat().st_size

            parser = get_parser(file_path)
            parse_result = parser.parse(file_path)

            quality = calculate_quality_score(parse_result)
            grade = quality_grade(quality)

            chunks_data = [
                {
                    "content": c.content,
                    "page_number": c.page_number,
                    "chapter": c.chapter,
                    "section": c.section,
                    "content_type": c.content_type,
                    "is_ocr": c.is_ocr,
                }
                for c in parse_result.chunks
            ]

            await save_parse_result(
                db=db,
                file=file,
                chunks_data=chunks_data,
                title=parse_result.title,
                author=parse_result.author,
                language=parse_result.language,
                total_pages=parse_result.total_pages,
                has_ocr_pages=parse_result.has_ocr_pages,
                parse_quality=quality,
                parse_status=grade,
                parse_error="; ".join(parse_result.errors) if parse_result.errors else None,
            )

            job.status = "success"
            job.finished_at = datetime.now(UTC)
            job.duration_ms = int(
                (job.finished_at - job.started_at).total_seconds() * 1000
            )
            job.details = {
                "chunks": len(chunks_data),
                "quality": quality,
                "grade": grade,
                "has_ocr_pages": parse_result.has_ocr_pages,
                "preprocess": preprocess_info,
            }

            await db.commit()

            return {
                "file_id": file_id,
                "status": grade,
                "chunks": len(chunks_data),
                "quality": quality,
                "has_ocr_pages": parse_result.has_ocr_pages,
            }

        except Exception as e:
            logger.exception(f"Parse failed for {file_id}")
            file.parse_status = "failed"
            file.parse_error = str(e)
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.error_message = str(e)

            await db.commit()

            return {"file_id": file_id, "status": "failed", "error": str(e)}


@celery_app.task(name="workers.tasks.parse_task.parse_file", bind=True, max_retries=2)
def parse_file(self, file_id: str) -> dict:
    result = asyncio.run(_parse_file(file_id))

    if result.get("status") in ("success", "partial"):
        # OCR이 필요한 페이지가 있으면 OCR 먼저, 완료 후 인덱싱
        if result.get("has_ocr_pages"):
            from workers.tasks.ocr_task import ocr_file
            # OCR 완료 후 index를 연쇄하기 위해 link 사용
            ocr_file.apply_async(
                args=[file_id],
                link=index_file_after_ocr.s(file_id),
            )
            logger.info(f"Chained OCR → index for: {file_id}")
        else:
            from workers.tasks.index_task import index_file
            index_file.delay(file_id)
            logger.info(f"Chained index task for: {file_id}")

    return result


@celery_app.task(name="workers.tasks.parse_task.index_file_after_ocr")
def index_file_after_ocr(ocr_result: dict, file_id: str) -> dict:
    """OCR 완료 후 인덱싱을 실행하는 콜백 태스크."""
    from workers.tasks.index_task import index_file
    logger.info(f"OCR done (processed={ocr_result.get('ocr_pages_processed', 0)}), indexing: {file_id}")
    return index_file(file_id)
