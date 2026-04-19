import hashlib
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chunk import Chunk
from app.models.file import File
from app.models.tag import Tag


def _compute_file_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            sha256.update(block)
    return sha256.hexdigest()


def _is_under_originals(path: Path) -> bool:
    """``documents_originals_root`` 하위 경로 여부. 스캔/감시 대상에서 제외하기 위함."""
    try:
        abs_path = path.resolve()
        originals = settings.documents_originals_root.resolve()
    except (OSError, RuntimeError):
        return False
    try:
        return abs_path.is_relative_to(originals)
    except ValueError:
        return False


def _detect_mime_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    mime_map = {
        ".pdf": "application/pdf",
        ".epub": "application/epub+zip",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".hwp": "application/x-hwp",
    }
    return mime_map.get(ext, "application/octet-stream")


async def register_file(db: AsyncSession, file_path: Path) -> File:
    """파일을 DB에 등록 (파싱 전 단계)."""
    abs_path = file_path.resolve()

    # 이미 등록된 파일인지 확인
    result = await db.execute(select(File).where(File.file_path == str(abs_path)))
    existing = result.scalar_one_or_none()

    file_hash = _compute_file_hash(abs_path)

    if existing:
        if existing.file_hash == file_hash:
            return existing
        # 해시가 변경되었으면 재파싱 대상
        existing.file_hash = file_hash
        existing.file_size = abs_path.stat().st_size
        existing.parse_status = "pending"
        existing.file_modified_at = datetime.fromtimestamp(abs_path.stat().st_mtime, tz=UTC)
        await db.flush()
        await db.refresh(existing)
        return existing

    file = File(
        file_path=str(abs_path),
        file_name=abs_path.name,
        file_size=abs_path.stat().st_size,
        file_hash=file_hash,
        format=abs_path.suffix.lstrip(".").lower(),
        mime_type=_detect_mime_type(abs_path),
        file_modified_at=datetime.fromtimestamp(abs_path.stat().st_mtime, tz=UTC),
    )
    db.add(file)
    await db.flush()
    await db.refresh(file)
    return file


async def save_upload(upload_bytes: bytes, filename: str) -> Path:
    """업로드된 파일을 DOCUMENT_ROOT에 저장."""
    dest = settings.document_root / filename
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        dest = settings.document_root / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"

    settings.document_root.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(upload_bytes)
    return dest


async def save_parse_result(
    db: AsyncSession,
    file: File,
    chunks_data: list[dict],
    title: str | None = None,
    author: str | None = None,
    language: str | None = None,
    total_pages: int | None = None,
    has_ocr_pages: bool = False,
    parse_quality: float = 0.0,
    parse_status: str = "success",
    parse_error: str | None = None,
) -> File:
    """파싱 결과를 DB에 저장."""
    file.title = title or file.file_name
    file.author = author
    file.language = language
    file.total_pages = total_pages
    file.has_ocr_pages = has_ocr_pages
    file.parse_quality = parse_quality
    file.parse_status = parse_status
    file.parse_error = parse_error
    file.parsed_at = datetime.now(UTC)

    # 기존 청크 삭제 후 새로 저장
    existing_chunks = await db.execute(select(Chunk).where(Chunk.file_id == file.file_id))
    for chunk in existing_chunks.scalars().all():
        await db.delete(chunk)

    for chunk_data in chunks_data:
        chunk = Chunk(
            file_id=file.file_id,
            page_number=chunk_data.get("page_number"),
            chapter=chunk_data.get("chapter"),
            section=chunk_data.get("section"),
            content=chunk_data["content"],
            content_type=chunk_data.get("content_type", "text"),
            is_ocr=chunk_data.get("is_ocr", False),
            char_count=len(chunk_data["content"]),
        )
        db.add(chunk)

    file.total_chunks = len(chunks_data)
    await db.flush()
    await db.refresh(file)
    return file


async def get_document(db: AsyncSession, file_id: uuid.UUID) -> File | None:
    result = await db.execute(select(File).where(File.file_id == file_id))
    return result.scalar_one_or_none()


async def list_documents(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    format_filter: str | None = None,
    status_filter: str | None = None,
) -> dict:
    query = select(File).order_by(File.created_at.desc())

    if format_filter:
        query = query.where(File.format == format_filter)
    if status_filter:
        query = query.where(File.parse_status == status_filter)

    # count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # paginate
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    files = list(result.scalars().all())

    return {"total": total, "page": page, "size": size, "items": files}


async def delete_document(db: AsyncSession, file_id: uuid.UUID) -> bool:
    file = await get_document(db, file_id)
    if file is None:
        return False

    # 원본 파일 삭제 (존재하면)
    file_path = Path(file.file_path)
    if file_path.exists():
        file_path.unlink()

    await db.delete(file)
    await db.flush()
    return True


async def scan_document_folder(db: AsyncSession) -> dict:
    """DOCUMENT_ROOT를 스캔하여 새 파일을 등록."""
    doc_root = settings.document_root
    if not doc_root.exists():
        return {"scanned": 0, "new": 0, "errors": []}

    supported_exts = {".pdf", ".epub", ".docx", ".txt", ".hwp"}
    scanned = 0
    new_count = 0
    errors = []

    for file_path in doc_root.rglob("*"):
        if file_path.suffix.lower() not in supported_exts:
            continue
        if not file_path.is_file():
            continue
        if _is_under_originals(file_path):
            # 보존된 원본은 재등록/재파싱 대상이 아님
            continue

        scanned += 1
        try:
            result = await db.execute(
                select(File).where(File.file_path == str(file_path.resolve()))
            )
            if result.scalar_one_or_none() is None:
                await register_file(db, file_path)
                new_count += 1
        except Exception as e:
            errors.append({"path": str(file_path), "error": str(e)})

    return {"scanned": scanned, "new": new_count, "errors": errors}
