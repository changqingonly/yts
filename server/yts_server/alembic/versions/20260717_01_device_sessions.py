"""Replace legacy access sessions with device-bound refresh sessions.

Revision ID: 20260717_01
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "20260717_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing access-only sessions cannot satisfy the new device/refresh contract.
    # Dropping them explicitly signs every device out during the security migration.
    if sa.inspect(op.get_bind()).has_table("user_session"):
        op.drop_table("user_session")
    op.create_table(
        "user_session",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("user_uuid", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("previous_refresh_token_hash", sa.String(64), nullable=True),
        sa.Column("refresh_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_refresh_request_id", sa.String(128), nullable=True),
        sa.Column("client_type", sa.String(32), nullable=False),
        sa.Column("device_name", sa.String(128), nullable=False),
        sa.Column("app_version", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_user_session_user_id", "user_session", ["user_id"])
    op.create_index("ix_user_session_user_uuid", "user_session", ["user_uuid"])
    op.create_index("ix_user_session_device_id", "user_session", ["device_id"])
    op.create_index("ix_user_session_expires_at", "user_session", ["expires_at"])
    op.create_index("ix_user_session_absolute_expires_at", "user_session", ["absolute_expires_at"])


def downgrade() -> None:
    raise RuntimeError("device session migration is intentionally irreversible")
