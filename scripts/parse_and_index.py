"""문서 파일을 동기적으로 파싱 + 인덱싱하는 스크립트 (Celery 불필요).

사용법:
    python -m scripts.parse_and_index                    # DOCUMENT_ROOT 전체 처리
    python -m scripts.parse_and_index --path /path/to/file.pdf  # 단일 파일
    python -m scripts.parse_and_index --dir tests/fixtures      # 특정 디렉토리
"""

import argparse
import asyncio
import logging
from pathlib import Path

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


async def process_file(db: AsyncSession, file_path: Path) -> dict:
    """단일 파일을 파싱 + 인덱싱."""
    logger.info(f"Processing: {file_path.name}")

    # 1. DB 등록
    file = await register_file(db, file_path)
    logger.info(f"  Registered: {file.file_id}")

    # 2. 파싱
    try:
        parser = get_parser(file_path)
        parse_result = parser.parse(file_path)
    except NotImplementedError as e:
        logger.warning(f"  Skipped (unsupported): {e}")
        return {"file": file_path.name, "status": "skipped", "reason": str(e)}

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
    )
    await db.commit()
    logger.info(f"  Parsed: {len(chunks_data)} chunks, quality={quality:.2f} ({grade})")

    # 3. 인덱싱
    try:
        idx_result = await index_document(db, file.file_id)
        await db.commit()
        logger.info(f"  Indexed: {idx_result['chunks_indexed']} chunks")
    except Exception as e:
        logger.error(f"  Index failed: {e}")
        return {"file": file_path.name, "status": grade, "chunks": len(chunks_data), "indexed": False}

    return {
        "file": file_path.name,
        "status": grade,
        "chunks": len(chunks_data),
        "quality": quality,
        "indexed": True,
    }


async def main_async(target_path: Path | None, target_dir: Path | None) -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        results = []

        if target_path:
            r = await process_file(db, target_path)
            results.append(r)
        else:
            scan_dir = target_dir or settings.document_root
            logger.info(f"Scanning: {scan_dir}")

            files = sorted(
                f for f in scan_dir.rglob("*")
                if f.suffix.lower() in SUPPORTED_EXTS and f.is_file()
            )
            logger.info(f"Found {len(files)} files")

            for file_path in files:
                r = await process_file(db, file_path)
                results.append(r)

        print("\n=== Summary ===")
        for r in results:
            status = r.get("status", "?")
            chunks = r.get("chunks", 0)
            indexed = "✓" if r.get("indexed") else "✗"
            print(f"  {r['file']}: {status} ({chunks} chunks) [{indexed}]")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, help="Single file to process")
    parser.add_argument("--dir", type=str, help="Directory to scan")
    args = parser.parse_args()

    target_path = Path(args.path) if args.path else None
    target_dir = Path(args.dir) if args.dir else None

    asyncio.run(main_async(target_path, target_dir))


if __name__ == "__main__":
    main()
