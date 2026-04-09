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
from app.parsers.quality_checker import calculate_quality_score, quality_grade
from app.services.document_service import save_parse_result
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
            job.details = {"chunks": len(chunks_data), "quality": quality, "grade": grade}

            await db.commit()

            return {
                "file_id": file_id,
                "status": grade,
                "chunks": len(chunks_data),
                "quality": quality,
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

    # 파싱 성공 시 자동으로 인덱싱 태스크 연쇄
    if result.get("status") in ("success", "partial"):
        from workers.tasks.index_task import index_file
        index_file.delay(file_id)
        logger.info(f"Chained index task for: {file_id}")

    return result
