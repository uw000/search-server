"""파일 감시 데몬: DOCUMENT_ROOT를 감시하여 새 파일 발견 시 파싱 큐에 등록.

사용법:
    python -m workers.file_watcher
"""

import asyncio
import logging
import os
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import settings
from app.services.document_service import register_file
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".pdf", ".epub", ".docx", ".txt", ".hwp"}


def _get_session_factory() -> async_sessionmaker:
    engine = create_async_engine(settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class DocumentEventHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        self._session_factory: async_sessionmaker | None = None

    def _get_factory(self) -> async_sessionmaker:
        if self._session_factory is None:
            self._session_factory = _get_session_factory()
        return self._session_factory

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle_file(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle_file(event.src_path)

    def _handle_file(self, path: str) -> None:
        file_path = Path(path)
        if file_path.suffix.lower() not in SUPPORTED_EXTS:
            return

        logger.info(f"Detected file: {file_path}")

        try:
            asyncio.run(self._register_and_queue(file_path))
        except Exception:
            logger.exception(f"Failed to process: {file_path}")

    async def _register_and_queue(self, file_path: Path) -> None:
        factory = self._get_factory()
        async with factory() as db:
            file = await register_file(db, file_path)
            await db.commit()
            logger.info(f"Registered: {file.file_name} ({file.file_id})")

            if file.parse_status == "pending":
                from workers.tasks.parse_task import parse_file
                parse_file.delay(str(file.file_id))
                logger.info(f"Queued parse task for: {file.file_id}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    watch_dir = os.environ.get("WATCH_DIR", str(settings.document_root))
    watch_path = Path(watch_dir)

    if not watch_path.exists():
        logger.info(f"Creating watch directory: {watch_path}")
        watch_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Watching: {watch_path}")

    handler = DocumentEventHandler()
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
