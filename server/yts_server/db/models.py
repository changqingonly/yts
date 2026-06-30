"""业务模型。两端 SQLite/PostgreSQL 共用。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .session import Base


class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    birthday: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text)
    agreement_accepted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserSession(Base):
    __tablename__ = "user_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditAccount(Base):
    __tablename__ = "credit_account"

    user_uuid: Mapped[str] = mapped_column(String(64), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
    frozen_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    change_amount: Mapped[int] = mapped_column(BigInteger)
    change_frozen_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    balance_after: Mapped[int] = mapped_column(BigInteger)
    frozen_balance_after: Mapped[int] = mapped_column(BigInteger, default=0)
    kind: Mapped[str] = mapped_column(String(32))
    biz_type: Mapped[str] = mapped_column(String(64))
    biz_id: Mapped[str] = mapped_column(String(128))
    reservation_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditGrantRecord(Base):
    __tablename__ = "credit_grant_record"
    __table_args__ = (UniqueConstraint("user_uuid", "grant_type", "grant_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    grant_type: Mapped[str] = mapped_column(String(64))
    grant_date: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditReservation(Base):
    __tablename__ = "credit_reservation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    reservation_key: Mapped[str] = mapped_column(String(128), unique=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), index=True)
    biz_type: Mapped[str] = mapped_column(String(64))
    biz_id: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyUsageCounter(Base):
    __tablename__ = "daily_usage_counter"
    __table_args__ = (UniqueConstraint("user_uuid", "scene", "usage_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    scene: Mapped[str] = mapped_column(String(64))
    usage_date: Mapped[datetime] = mapped_column(Date)
    used: Mapped[int] = mapped_column(Integer, default=0)
    limit: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CreationJob(Base):
    __tablename__ = "creation_job"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SongPrompt(Base):
    __tablename__ = "song_prompt"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    from_llm: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SongDetail(Base):
    __tablename__ = "song_detail"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    prompt_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("song_prompt.id"), index=True)
    lyric_prompt: Mapped[str] = mapped_column(Text)
    style_prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SongAsset(Base):
    __tablename__ = "song_asset"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    song_id: Mapped[int] = mapped_column(BigInteger, index=True)
    asset_type: Mapped[str] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MusicPlaylist(Base):
    __tablename__ = "music_playlist"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)


class MusicPlaylistItem(Base):
    __tablename__ = "music_playlist_item"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    playlist_id: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(64))
    source_ref: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    position: Mapped[float] = mapped_column(Float)
    added_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)
    deleted_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    op_clock: Mapped[int] = mapped_column(BigInteger)
    device_id: Mapped[str] = mapped_column(String(128))
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)


class LocalImportBlob(Base):
    __tablename__ = "local_import_blob"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(128))
    path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LocalImportOwner(Base):
    __tablename__ = "local_import_owner"
    __table_args__ = (UniqueConstraint("hash", "user_uuid"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    hash: Mapped[str] = mapped_column(String(64), index=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
