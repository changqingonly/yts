"""Persist generated music cover theme colors.

Revision ID: 20260801_01
Revises: 20260729_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20260801_01"
down_revision = "20260729_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("music_cover_job", sa.Column("theme_color", sa.String(7), nullable=True))


def downgrade() -> None:
    op.drop_column("music_cover_job", "theme_color")
