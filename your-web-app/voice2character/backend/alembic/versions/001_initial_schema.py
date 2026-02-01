"""初期スキーマ作成

jobs, transcription_segments テーブルを作成する。

Revision ID: 001
Revises:
Create Date: 2025-02-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # jobsテーブル
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="uploading"),
        sa.Column("progress", sa.Float(), server_default="0.0"),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("language", sa.String(), server_default="ja"),
        sa.Column("whisper_model", sa.String(), nullable=True),
        sa.Column("whisper_device", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # transcription_segmentsテーブル
    op.create_table(
        "transcription_segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transcription_segments_job_id",
        "transcription_segments",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transcription_segments_job_id",
        table_name="transcription_segments",
    )
    op.drop_table("transcription_segments")
    op.drop_table("jobs")
