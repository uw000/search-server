import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class File(TimestampMixin, Base):
    __tablename__ = "files"

    file_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    file_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    format: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))

    parse_status: Mapped[str] = mapped_column(String(20), default="pending")
    parse_quality: Mapped[float] = mapped_column(Float, default=0.0)
    parse_error: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10))
    total_pages: Mapped[int | None] = mapped_column(Integer)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    has_ocr_pages: Mapped[bool] = mapped_column(Boolean, default=False)

    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    index_version: Mapped[int] = mapped_column(Integer, default=0)

    file_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="file", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(back_populates="file", cascade="all, delete-orphan")
    bookmarks: Mapped[list["Bookmark"]] = relationship(back_populates="file", cascade="all, delete-orphan")
    job_logs: Mapped[list["JobLog"]] = relationship(back_populates="file")
