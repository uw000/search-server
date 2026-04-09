import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SearchHistory(Base):
    __tablename__ = "search_history"

    search_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    result_count: Mapped[int | None] = mapped_column(Integer)
    took_ms: Mapped[int | None] = mapped_column(Integer)
    filters: Mapped[dict | None] = mapped_column(JSONB)
    searched_at: Mapped[datetime] = mapped_column(default=func.now())

    user: Mapped["User | None"] = relationship(back_populates="search_history")
