"""Add local music cover generation lifecycle.

Revision ID: 20260729_01
Revises: 20260726_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20260729_01"
down_revision = "20260726_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "music_cover_policy",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("user_uuid", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("generation_epoch", sa.Integer(), nullable=False),
        sa.Column("auto_cover_state", sa.String(32), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("user_uuid", "content_hash"),
    )
    op.create_table(
        "music_cover_job",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_uuid", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("generation_epoch", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("trigger_source", sa.String(32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("started_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("finished_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("user_uuid", "content_hash", "generation_epoch"),
    )
    op.create_index("ix_music_cover_job_status", "music_cover_job", ["status"])
    op.create_table(
        "music_cover_operation",
        sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column("user_uuid", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("music_cover_operation")
    op.drop_index("ix_music_cover_job_status", table_name="music_cover_job")
    op.drop_table("music_cover_job")
    op.drop_table("music_cover_policy")
