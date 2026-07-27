"""Add durable canonical audio playback renditions.

Revision ID: 20260726_01
Revises: 20260717_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_01"
down_revision = "20260717_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audio_playback_rendition",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column(
            "original_content_hash",
            sa.String(64),
            sa.ForeignKey("local_import_blob.hash"),
            nullable=False,
        ),
        sa.Column("profile", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("output_mime", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("original_content_hash", "profile"),
    )
    op.create_index(
        "ix_audio_playback_rendition_original_content_hash",
        "audio_playback_rendition",
        ["original_content_hash"],
    )
    op.create_index(
        "ix_audio_playback_rendition_status",
        "audio_playback_rendition",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_audio_playback_rendition_status", table_name="audio_playback_rendition")
    op.drop_index(
        "ix_audio_playback_rendition_original_content_hash",
        table_name="audio_playback_rendition",
    )
    op.drop_table("audio_playback_rendition")
