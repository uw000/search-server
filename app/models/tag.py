import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Tag(Base):
    __tablename__ = "tags"

    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.file_id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(100), primary_key=True)

    file: Mapped["File"] = relationship(back_populates="tags")
