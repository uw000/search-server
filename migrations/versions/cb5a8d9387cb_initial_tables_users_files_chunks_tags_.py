"""Initial tables: users, files, chunks, tags, job_log, bookmarks, search_history

Revision ID: cb5a8d9387cb
Revises:
Create Date: 2026-04-10 01:00:15.721724

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "cb5a8d9387cb"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("user_id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    # files
    op.create_table(
        "files",
        sa.Column("file_id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("parse_quality", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("has_ocr_pages", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("index_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("file_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("file_id"),
        sa.UniqueConstraint("file_path"),
    )
    op.create_index("idx_files_format", "files", ["format"])
    op.create_index("idx_files_parse_status", "files", ["parse_status"])
    op.create_index("idx_files_hash", "files", ["file_hash"])

    # chunks
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chapter", sa.Text(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("is_ocr", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"], ondelete="CASCADE"),
    )
    op.create_index("idx_chunks_file_id", "chunks", ["file_id"])
    op.create_index("idx_chunks_file_page", "chunks", ["file_id", "page_number"])

    # tags
    op.create_table(
        "tags",
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("file_id", "tag"),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"], ondelete="CASCADE"),
    )
    op.create_index("idx_tags_tag", "tags", ["tag"])

    # job_log
    op.create_table(
        "job_log",
        sa.Column("job_id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("job_id"),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"], ondelete="SET NULL"),
    )
    op.create_index("idx_job_log_file", "job_log", ["file_id"])
    op.create_index("idx_job_log_status", "job_log", ["status"])
    op.create_index("idx_job_log_type", "job_log", ["job_type"])

    # search_history
    op.create_table(
        "search_history",
        sa.Column("search_id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("took_ms", sa.Integer(), nullable=True),
        sa.Column("filters", postgresql.JSONB(), nullable=True),
        sa.Column("searched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("search_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="SET NULL"),
    )

    # bookmarks
    op.create_table(
        "bookmarks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "file_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("bookmarks")
    op.drop_table("search_history")
    op.drop_index("idx_job_log_type", table_name="job_log")
    op.drop_index("idx_job_log_status", table_name="job_log")
    op.drop_index("idx_job_log_file", table_name="job_log")
    op.drop_table("job_log")
    op.drop_index("idx_tags_tag", table_name="tags")
    op.drop_table("tags")
    op.drop_index("idx_chunks_file_page", table_name="chunks")
    op.drop_index("idx_chunks_file_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("idx_files_hash", table_name="files")
    op.drop_index("idx_files_parse_status", table_name="files")
    op.drop_index("idx_files_format", table_name="files")
    op.drop_table("files")
    op.drop_table("users")
