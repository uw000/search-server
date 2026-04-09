"""기존 문서 폴더를 일괄 임포트하는 스크립트.

DOCUMENT_ROOT를 스캔하여 새 파일을 DB에 등록하고, 파싱+인덱싱을 수행합니다.

사용법:
    python -m scripts.bulk_import
    python -m scripts.bulk_import --dir /path/to/documents
    python -m scripts.bulk_import --workers 4
"""

import argparse
import asyncio
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.file import File
from app.parsers import get_parser
from app.parsers.quality_checker import calculate_quality_score, quality_grade
from app.services.document_service import register_file, save_parse_result
from app.services.index_service import index_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".pdf", ".epub", ".docx", ".txt"}


async def process_single(db: AsyncSession, file_path: Path) -> dict:
    """단일 파일을 등록 → 파싱 → 인덱싱."""
    try:
        file = await register_file(db, file_path)

        # 이미 파싱 완료된 파일은 스킵
        if file.parse_status in ("success", "partial") and file.indexed_at is not None:
            return {"file": file_path.name, "status": "already_done"}

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
            db=db, file=file, chunks_data=chunks_data,
            title=parse_result.title, author=parse_result.author,
            language=parse_result.language, total_pages=parse_result.total_pages,
            has_ocr_pages=parse_result.has_ocr_pages,
            parse_quality=quality, parse_status=grade,
        )
        await db.commit()

        idx = await index_document(db, file.file_id)
        await db.commit()

        return {
            "file": file_path.name, "status": grade,
            "chunks": len(chunks_data), "quality": quality,
        }
    except NotImplementedError:
        return {"file": file_path.name, "status": "unsupported"}
    except Exception as e:
        logger.error(f"Failed: {file_path.name}: {e}")
        return {"file": file_path.name, "status": "error", "error": str(e)}


async def run(scan_dir: Path) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    files = sorted(
        f for f in scan_dir.rglob("*")
        if f.suffix.lower() in SUPPORTED_EXTS and f.is_file()
    )
    logger.info(f"Found {len(files)} files in {scan_dir}")

    results = {"success": 0, "partial": 0, "failed": 0, "error": 0, "unsupported": 0, "already_done": 0}

    async with factory() as db:
        for i, file_path in enumerate(files, 1):
            r = await process_single(db, file_path)
            status = r["status"]
            results[status] = results.get(status, 0) + 1

            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(files)}")

    await engine.dispose()

    print("\n=== Bulk Import Summary ===")
    for k, v in results.items():
        if v > 0:
            print(f"  {k}: {v}")
    print(f"  Total files: {len(files)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk import documents")
    parser.add_argument("--dir", type=str, default=None, help="Directory to scan")
    args = parser.parse_args()

    scan_dir = Path(args.dir) if args.dir else settings.document_root
    asyncio.run(run(scan_dir))


if __name__ == "__main__":
    main()
