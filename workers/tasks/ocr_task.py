import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.chunk import Chunk
from app.models.file import File
from app.models.job_log import JobLog
from app.parsers.ocr_processor import ocr_pdf_page
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_session_factory() -> async_sessionmaker:
    engine = create_async_engine(settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _ocr_file(file_id: str) -> dict:
    session_factory = _get_session_factory()

    async with session_factory() as db:
        result = await db.execute(select(File).where(File.file_id == uuid.UUID(file_id)))
        file = result.scalar_one_or_none()
        if file is None:
            return {"error": f"File not found: {file_id}"}

        if file.format != "pdf":
            return {"error": "OCR is only supported for PDF files"}

        job = JobLog(
            file_id=file.file_id,
            job_type="ocr",
            status="running",
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.commit()

        try:
            # OCR이 필요한 청크 찾기
            chunk_result = await db.execute(
                select(Chunk).where(
                    Chunk.file_id == file.file_id,
                    Chunk.is_ocr.is_(True),
                )
            )
            ocr_chunks = chunk_result.scalars().all()

            file_path = Path(file.file_path)
            processed = 0

            for chunk in ocr_chunks:
                if chunk.page_number is None:
                    continue

                text = ocr_pdf_page(file_path, chunk.page_number)
                if text.strip():
                    chunk.content = text
                    chunk.char_count = len(text)
                    processed += 1

            job.status = "success"
            job.finished_at = datetime.now(UTC)
            job.duration_ms = int(
                (job.finished_at - job.started_at).total_seconds() * 1000
            )
            job.details = {"ocr_pages_processed": processed}

            await db.commit()

            return {
                "file_id": file_id,
                "status": "success",
                "ocr_pages_processed": processed,
            }

        except Exception as e:
            logger.exception(f"OCR failed for {file_id}")
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.error_message = str(e)

            await db.commit()

            return {"file_id": file_id, "status": "failed", "error": str(e)}


@celery_app.task(name="workers.tasks.ocr_task.ocr_file", bind=True, max_retries=1)
def ocr_file(self, file_id: str) -> dict:
    return asyncio.run(_ocr_file(file_id))
