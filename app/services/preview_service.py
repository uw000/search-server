import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chunk import Chunk
from app.models.file import File


def _safe_file_path(file_path: str) -> Path:
    """파일 경로 검증: DOCUMENT_ROOT 내부인지 확인."""
    path = Path(file_path).resolve()
    doc_root = settings.document_root.resolve()
    if not path.is_relative_to(doc_root):
        raise PermissionError(f"Access denied: file is outside document root")
    return path


async def get_text_preview(
    db: AsyncSession,
    file_id: uuid.UUID,
    page_num: int,
    context_pages: int = 1,
) -> dict:
    """해당 페이지 ± context_pages의 텍스트 반환."""
    start_page = max(1, page_num - context_pages)
    end_page = page_num + context_pages

    result = await db.execute(
        select(Chunk)
        .where(
            Chunk.file_id == file_id,
            Chunk.page_number >= start_page,
            Chunk.page_number <= end_page,
        )
        .order_by(Chunk.page_number)
    )
    chunks = result.scalars().all()

    pages = []
    for chunk in chunks:
        pages.append({
            "page_number": chunk.page_number,
            "content": chunk.content,
            "content_type": chunk.content_type,
            "is_ocr": chunk.is_ocr,
        })

    return {
        "file_id": str(file_id),
        "requested_page": page_num,
        "pages": pages,
    }


async def get_image_preview(
    db: AsyncSession,
    file_id: uuid.UUID,
    page_num: int,
    dpi: int = 150,
) -> bytes | None:
    """PDF 페이지를 이미지(JPEG)로 렌더링."""
    result = await db.execute(select(File).where(File.file_id == file_id))
    file = result.scalar_one_or_none()
    if file is None or file.format != "pdf":
        return None

    file_path = _safe_file_path(file.file_path)
    if not file_path.exists():
        return None

    # 캐시 확인
    cache_dir = settings.preview_cache / str(file_id)
    cache_file = cache_dir / f"page_{page_num}_dpi{dpi}.jpg"

    if cache_file.exists():
        return cache_file.read_bytes()

    # PyMuPDF로 렌더링
    import fitz

    doc = fitz.open(str(file_path))
    if page_num < 1 or page_num > len(doc):
        doc.close()
        return None

    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)

    # JPEG로 변환
    image_bytes = pix.tobytes("jpeg")
    doc.close()

    # 캐시 저장
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(image_bytes)

    return image_bytes


async def get_download_path(
    db: AsyncSession,
    file_id: uuid.UUID,
) -> tuple[Path, str] | None:
    """원본 파일 다운로드 경로 반환."""
    result = await db.execute(select(File).where(File.file_id == file_id))
    file = result.scalar_one_or_none()
    if file is None:
        return None

    file_path = _safe_file_path(file.file_path)
    if not file_path.exists():
        return None

    return file_path, file.file_name
