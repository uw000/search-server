import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.file import File
from app.models.job_log import JobLog
from app.services.index_service import index_document
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_session_factory() -> async_sessionmaker:
    engine = create_async_engine(settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _index_file(file_id: str) -> dict:
    session_factory = _get_session_factory()

    async with session_factory() as db:
        result = await db.execute(select(File).where(File.file_id == uuid.UUID(file_id)))
        file = result.scalar_one_or_none()
        if file is None:
            return {"error": f"File not found: {file_id}"}

        job = JobLog(
            file_id=file.file_id,
            job_type="index",
            status="running",
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.commit()

        try:
            result = await index_document(db, file.file_id)

            job.status = "success"
            job.finished_at = datetime.now(UTC)
            job.duration_ms = int(
                (job.finished_at - job.started_at).total_seconds() * 1000
            )
            job.details = result

            await db.commit()

            return {"file_id": file_id, "status": "success", **result}

        except Exception as e:
            logger.exception(f"Index failed for {file_id}")
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.error_message = str(e)

            await db.commit()

            return {"file_id": file_id, "status": "failed", "error": str(e)}


@celery_app.task(name="workers.tasks.index_task.index_file", bind=True, max_retries=2)
def index_file(self, file_id: str) -> dict:
    return asyncio.run(_index_file(file_id))
