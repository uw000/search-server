"""PostgreSQL 데이터를 기반으로 OpenSearch 인덱스를 재구축하는 스크립트.

사용법:
    python -m scripts.rebuild_index              # 전체 재구축
    python -m scripts.rebuild_index --recreate   # 인덱스 삭제 후 재생성
"""

import argparse
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.file import File
from app.opensearch.client import close_opensearch_client
from app.opensearch.index_manager import recreate_index, CHUNKS_INDEX, DOCUMENTS_INDEX
from app.services.index_service import index_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def rebuild(recreate: bool) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    if recreate:
        logger.info("Recreating indices...")
        await recreate_index(DOCUMENTS_INDEX)
        await recreate_index(CHUNKS_INDEX)
        logger.info("Indices recreated.")

    async with factory() as db:
        result = await db.execute(
            select(File).where(File.parse_status.in_(["success", "partial"]))
        )
        files = result.scalars().all()
        logger.info(f"Found {len(files)} parseable documents to index")

        indexed = 0
        errors = 0
        for i, file in enumerate(files, 1):
            try:
                await index_document(db, file.file_id)
                await db.commit()
                indexed += 1
            except Exception as e:
                logger.error(f"Failed to index {file.file_name}: {e}")
                errors += 1

            if i % 50 == 0:
                logger.info(f"Progress: {i}/{len(files)}")

    await close_opensearch_client()
    await engine.dispose()

    print(f"\n=== Rebuild Summary ===")
    print(f"  Indexed: {indexed}")
    print(f"  Errors: {errors}")
    print(f"  Total: {len(files)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild OpenSearch index from PostgreSQL")
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate indices first")
    args = parser.parse_args()

    asyncio.run(rebuild(args.recreate))


if __name__ == "__main__":
    main()
