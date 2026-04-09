import uuid
from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    bookmarks: Mapped[list["Bookmark"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    search_history: Mapped[list["SearchHistory"]] = relationship(back_populates="user")
