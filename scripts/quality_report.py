"""파싱 품질 리포트를 생성하는 스크립트.

사용법:
    python -m scripts.quality_report
    python -m scripts.quality_report --format pdf
    python -m scripts.quality_report --status failed
"""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.file import File


async def generate_report(format_filter: str | None, status_filter: str | None) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        query = select(File).order_by(File.parse_quality.desc())

        if format_filter:
            query = query.where(File.format == format_filter)
        if status_filter:
            query = query.where(File.parse_status == status_filter)

        result = await db.execute(query)
        files = result.scalars().all()

        if not files:
            print("No documents found.")
            await engine.dispose()
            return

        # 통계
        total = len(files)
        avg_quality = sum(f.parse_quality for f in files) / total
        status_counts: dict[str, int] = {}
        format_counts: dict[str, int] = {}
        total_chunks = 0

        for f in files:
            status_counts[f.parse_status] = status_counts.get(f.parse_status, 0) + 1
            format_counts[f.format] = format_counts.get(f.format, 0) + 1
            total_chunks += f.total_chunks

        print("=" * 60)
        print("파싱 품질 리포트")
        print("=" * 60)
        print(f"\n총 문서: {total}")
        print(f"총 청크: {total_chunks}")
        print(f"평균 품질: {avg_quality:.3f}")
        print(f"\n상태별:")
        for s, c in sorted(status_counts.items()):
            print(f"  {s}: {c}")
        print(f"\n포맷별:")
        for f, c in sorted(format_counts.items()):
            print(f"  {f}: {c}")

        # 낮은 품질 문서
        low_quality = [f for f in files if f.parse_quality < 0.7]
        if low_quality:
            print(f"\n--- 낮은 품질 (< 0.7): {len(low_quality)}건 ---")
            for f in low_quality[:20]:
                error = f" | {f.parse_error[:50]}" if f.parse_error else ""
                print(f"  [{f.parse_quality:.2f}] {f.file_name} ({f.format}){error}")

        # 상세 목록 (상위 20건)
        print(f"\n--- 전체 목록 (상위 20건) ---")
        print(f"{'Quality':>8} {'Status':>10} {'Format':>6} {'Chunks':>6} {'Name'}")
        print("-" * 60)
        for f in files[:20]:
            print(f"{f.parse_quality:>8.3f} {f.parse_status:>10} {f.format:>6} {f.total_chunks:>6} {f.file_name}")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate parsing quality report")
    parser.add_argument("--format", type=str, help="Filter by format (pdf, epub, docx, txt)")
    parser.add_argument("--status", type=str, help="Filter by status (success, partial, failed)")
    args = parser.parse_args()

    asyncio.run(generate_report(args.format, args.status))


if __name__ == "__main__":
    main()
