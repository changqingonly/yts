"""业务模型。两端 SQLite/PostgreSQL 共用。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
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

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_account.id"), index=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64))
    previous_refresh_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refresh_generation: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_refresh_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_refresh_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_type: Mapped[str] = mapped_column(String(32), default="web")
    device_name: Mapped[str] = mapped_column(String(128), default="Web browser")
    app_version: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
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


class WorkflowRunHistory(Base):
    __tablename__ = "workflow_run_history"
    __table_args__ = (UniqueConstraint("workflow_id", "user_uuid", "thread_id"),)

    id: Mapped[str] = mapped_column(String(320), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(128), index=True)
    user_uuid: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    user_prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    completed_nodes: Mapped[int] = mapped_column(Integer, default=0)
    total_nodes: Mapped[int] = mapped_column(Integer, default=0)
    last_node_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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


class MetaSong(Base):
    __tablename__ = "meta_song"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(128))
    file_format: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bit_rate_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec_name: Mapped[str] = mapped_column(String(128))
    codec_profile: Mapped[str | None] = mapped_column(String(128), nullable=True)
    container_format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extracted_at_ms: Mapped[int] = mapped_column(BigInteger)
    extractor_name: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(64))
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)


class MusicPlaylist(Base):
    __tablename__ = "music_playlist"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(32), index=True, default="cloud")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)
    deleted_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    op_clock: Mapped[int] = mapped_column(BigInteger, default=0)


class MusicPlaylistItem(Base):
    __tablename__ = "music_playlist_item"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    playlist_id: Mapped[str] = mapped_column(String(128), index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    title_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artist_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    added_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)
    deleted_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    op_clock: Mapped[int] = mapped_column(BigInteger)
    device_id: Mapped[str] = mapped_column(String(128))
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
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


class AudioPlaybackRendition(Base):
    __tablename__ = "audio_playback_rendition"
    __table_args__ = (UniqueConstraint("original_content_hash", "profile"),)

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    original_content_hash: Mapped[str] = mapped_column(
        String(64), ForeignKey("local_import_blob.hash"), index=True
    )
    profile: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)


class MusicCoverPolicy(Base):
    __tablename__ = "music_cover_policy"
    __table_args__ = (UniqueConstraint("user_uuid", "content_hash"),)

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    generation_epoch: Mapped[int] = mapped_column(Integer, default=1)
    auto_cover_state: Mapped[str] = mapped_column(String(32), default="enabled")
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)


class MusicCoverJob(Base):
    __tablename__ = "music_cover_job"
    __table_args__ = (UniqueConstraint("user_uuid", "content_hash", "generation_epoch"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    generation_epoch: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[int] = mapped_column(Integer)
    trigger_source: Mapped[str] = mapped_column(String(32))
    prompt: Mapped[str] = mapped_column(Text)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    started_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finished_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)


class MusicCoverOperation(Base):
    __tablename__ = "music_cover_operation"

    request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32))
    job_id: Mapped[str] = mapped_column(String(64))
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
