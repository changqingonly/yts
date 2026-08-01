from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from yts_core.config import Profile, get_settings
from yts_core.inference.gateway_adapter import GatewayInference

from ..db.models import (
    LocalImportOwner,
    MusicCoverJob,
    MusicCoverOperation,
    MusicCoverPolicy,
    MusicPlaylistItem,
)
from ..errors import AppError
from .cover_color import extract_theme_color

QUEUED = "queued"
GENERATING = "generating"
READY = "ready"
FAILED = "failed"
CANCELLED = "cancelled"
ENABLED = "enabled"
SUPPRESSED = "suppressed"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


async def ensure_cover(
    session: AsyncSession, *, user_uuid: str, content_hash: str, trigger_source: str
) -> dict:
    _require_local_profile()
    if trigger_source not in {"system", "user"}:
        raise AppError.bad_request(
            "invalid_cover_trigger", "trigger_source must be system or user", "trigger_source"
        )
    await _require_owner(session, user_uuid, content_hash)
    policy = await _get_or_create_policy(session, user_uuid, content_hash)
    if policy.auto_cover_state == SUPPRESSED:
        return _suppressed_response(content_hash, policy.generation_epoch)
    existing_job = await _job_for_epoch(
        session, user_uuid, content_hash, policy.generation_epoch, required=False
    )
    if existing_job is not None and existing_job.status == READY:
        return _job_response(existing_job)
    image_available, unavailable_reason = await GatewayInference().image_status()
    if not image_available:
        return {
            "content_hash": content_hash,
            "generation_epoch": policy.generation_epoch,
            "status": "unavailable",
            "error_code": "local_image_model_unavailable",
            "error_message": unavailable_reason,
            "cover_url": None,
        }
    priority = 100 if trigger_source == "user" else 10
    prompt = await _cover_prompt(session, user_uuid, content_hash)
    job_id = f"cover_{uuid.uuid4().hex}"
    now = _now_ms()
    statement = sqlite_insert(MusicCoverJob).values(
        id=job_id,
        user_uuid=user_uuid,
        content_hash=content_hash,
        generation_epoch=policy.generation_epoch,
        status=QUEUED,
        priority=priority,
        trigger_source=trigger_source,
        prompt=prompt,
        attempt_count=0,
        created_at_ms=now,
        updated_at_ms=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["user_uuid", "content_hash", "generation_epoch"],
        set_={"priority": priority, "updated_at_ms": now},
        where=MusicCoverJob.priority < priority,
    )
    await session.execute(statement)
    await session.flush()
    job = await _job_for_epoch(session, user_uuid, content_hash, policy.generation_epoch)
    await session.refresh(job)
    return _job_response(job)


async def regenerate_cover(
    session: AsyncSession, *, user_uuid: str, content_hash: str, request_id: str
) -> dict:
    _require_local_profile()
    if not request_id.strip():
        raise AppError.bad_request(
            "cover_request_id_required", "request_id must not be empty", "request_id"
        )
    await _require_owner(session, user_uuid, content_hash)
    operation = await session.get(MusicCoverOperation, request_id)
    if operation is not None:
        if operation.user_uuid != user_uuid or operation.content_hash != content_hash:
            raise AppError.conflict(
                "cover_request_id_conflict", "request_id belongs to another cover operation"
            )
        job = await session.get(MusicCoverJob, operation.job_id)
        if job is None:
            raise RuntimeError("cover operation references missing job")
        return _job_response(job)
    policy = await _get_or_create_policy(session, user_uuid, content_hash)
    policy.generation_epoch += 1
    policy.auto_cover_state = ENABLED
    policy.updated_at_ms = _now_ms()
    await session.flush()
    response = await ensure_cover(
        session, user_uuid=user_uuid, content_hash=content_hash, trigger_source="user"
    )
    session.add(
        MusicCoverOperation(
            request_id=request_id,
            user_uuid=user_uuid,
            content_hash=content_hash,
            action="regenerate",
            job_id=response["job_id"],
            created_at_ms=_now_ms(),
        )
    )
    await session.flush()
    return response


async def delete_cover(session: AsyncSession, *, user_uuid: str, content_hash: str) -> dict:
    _require_local_profile()
    await _require_owner(session, user_uuid, content_hash)
    policy = await _get_or_create_policy(session, user_uuid, content_hash)
    policy.auto_cover_state = SUPPRESSED
    policy.updated_at_ms = _now_ms()
    jobs = (
        (
            await session.execute(
                select(MusicCoverJob).where(
                    MusicCoverJob.user_uuid == user_uuid,
                    MusicCoverJob.content_hash == content_hash,
                )
            )
        )
        .scalars()
        .all()
    )
    for job in jobs:
        if job.status in {QUEUED, GENERATING}:
            job.status = CANCELLED
            job.finished_at_ms = _now_ms()
        if job.output_path:
            Path(job.output_path).unlink(missing_ok=True)
            job.output_path = None
            job.output_hash = None
            job.theme_color = None
    await session.flush()
    return _suppressed_response(content_hash, policy.generation_epoch)


async def retry_cover(session: AsyncSession, *, user_uuid: str, content_hash: str) -> dict:
    _require_local_profile()
    await _require_owner(session, user_uuid, content_hash)
    policy = await _get_or_create_policy(session, user_uuid, content_hash)
    job = await _job_for_epoch(session, user_uuid, content_hash, policy.generation_epoch)
    if job.status != FAILED:
        raise AppError.conflict(
            "music_cover_not_failed",
            f"only failed music cover can retry; current state is {job.status}",
        )
    job.status = QUEUED
    job.priority = 100
    job.trigger_source = "user"
    job.error_code = None
    job.error_message = None
    job.output_path = None
    job.output_hash = None
    job.theme_color = None
    job.started_at_ms = None
    job.finished_at_ms = None
    job.updated_at_ms = _now_ms()
    await session.flush()
    return _job_response(job)


async def cover_status(session: AsyncSession, *, user_uuid: str, content_hash: str) -> dict:
    _require_local_profile()
    await _require_owner(session, user_uuid, content_hash)
    policy = await _get_or_create_policy(session, user_uuid, content_hash)
    if policy.auto_cover_state == SUPPRESSED:
        return _suppressed_response(content_hash, policy.generation_epoch)
    job = await _job_for_epoch(
        session, user_uuid, content_hash, policy.generation_epoch, required=False
    )
    if job is None:
        return {
            "content_hash": content_hash,
            "generation_epoch": policy.generation_epoch,
            "status": "absent",
        }
    return _job_response(job)


async def cover_file(session: AsyncSession, *, user_uuid: str, content_hash: str) -> Path:
    status = await cover_status(session, user_uuid=user_uuid, content_hash=content_hash)
    if status["status"] != READY:
        raise AppError.conflict("music_cover_not_ready", f"music cover is {status['status']}")
    job = await session.get(MusicCoverJob, status["job_id"])
    if job is None or not job.output_path:
        raise RuntimeError("ready music cover is missing artifact metadata")
    path = Path(job.output_path)
    if not path.is_file():
        raise AppError.not_found("music_cover_file_missing", "music cover file not found")
    return path


async def process_next_cover_job(sessionmaker: async_sessionmaker) -> bool:
    async with sessionmaker() as session:
        job_id = (
            await session.execute(
                select(MusicCoverJob.id)
                .where(MusicCoverJob.status == QUEUED)
                .order_by(MusicCoverJob.priority.desc(), MusicCoverJob.created_at_ms.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if job_id is None:
        return False
    if not await _claim_job(sessionmaker, job_id):
        return True
    try:
        async with sessionmaker() as session:
            job = await session.get(MusicCoverJob, job_id)
            if job is None:
                raise RuntimeError("claimed music cover job is missing")
            prompt = job.prompt
        png = await GatewayInference().generate_image(prompt, width=768, height=768, steps=4)
        if not png.startswith(PNG_SIGNATURE):
            raise ValueError("image generator returned invalid PNG data")
        theme_color = extract_theme_color(png)
        output_dir = Path(get_settings().music_cover_storage_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(png).hexdigest()
        final_path = output_dir / f"{job_id}-{digest}.png"
        temporary_path = output_dir / f".{job_id}.tmp"
        temporary_path.write_bytes(png)
        temporary_path.replace(final_path)
        accepted = await _mark_ready(sessionmaker, job_id, final_path, digest, theme_color)
        if not accepted:
            final_path.unlink(missing_ok=True)
    except Exception as error:
        await _mark_failed(sessionmaker, job_id, type(error).__name__, str(error))
    return True


async def run_cover_worker(*, stop_event: asyncio.Event, wake_event: asyncio.Event) -> None:
    from ..db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    while True:
        await wake_event.wait()
        wake_event.clear()
        if stop_event.is_set():
            return
        while await process_next_cover_job(sessionmaker):
            if stop_event.is_set():
                return


async def _claim_job(sessionmaker: async_sessionmaker, job_id: str) -> bool:
    async with sessionmaker() as session:
        result = await session.execute(
            update(MusicCoverJob)
            .where(MusicCoverJob.id == job_id, MusicCoverJob.status == QUEUED)
            .values(
                status=GENERATING,
                attempt_count=MusicCoverJob.attempt_count + 1,
                started_at_ms=_now_ms(),
                updated_at_ms=_now_ms(),
            )
        )
        await session.commit()
        return result.rowcount == 1


async def _mark_ready(
    sessionmaker, job_id: str, path: Path, digest: str, theme_color: str
) -> bool:
    async with sessionmaker() as session:
        result = await session.execute(
            update(MusicCoverJob)
            .where(MusicCoverJob.id == job_id, MusicCoverJob.status == GENERATING)
            .values(
                status=READY,
                output_path=str(path),
                output_hash=digest,
                theme_color=theme_color,
                finished_at_ms=_now_ms(),
                updated_at_ms=_now_ms(),
            )
        )
        await session.commit()
        return result.rowcount == 1


async def _mark_failed(sessionmaker, job_id: str, code: str, message: str) -> None:
    async with sessionmaker() as session:
        await session.execute(
            update(MusicCoverJob)
            .where(MusicCoverJob.id == job_id, MusicCoverJob.status == GENERATING)
            .values(
                status=FAILED,
                error_code=code[:64],
                error_message=message,
                finished_at_ms=_now_ms(),
                updated_at_ms=_now_ms(),
            )
        )
        await session.commit()


async def _get_or_create_policy(session, user_uuid: str, content_hash: str) -> MusicCoverPolicy:
    policy_id = f"{user_uuid}:{content_hash}"
    policy = await session.get(MusicCoverPolicy, policy_id)
    if policy is None:
        now = _now_ms()
        policy = MusicCoverPolicy(
            id=policy_id,
            user_uuid=user_uuid,
            content_hash=content_hash,
            generation_epoch=1,
            auto_cover_state=ENABLED,
            created_at_ms=now,
            updated_at_ms=now,
        )
        session.add(policy)
        await session.flush()
    return policy


async def _job_for_epoch(
    session, user_uuid: str, content_hash: str, epoch: int, *, required: bool = True
) -> MusicCoverJob | None:
    job = (
        await session.execute(
            select(MusicCoverJob).where(
                MusicCoverJob.user_uuid == user_uuid,
                MusicCoverJob.content_hash == content_hash,
                MusicCoverJob.generation_epoch == epoch,
            )
        )
    ).scalar_one_or_none()
    if required and job is None:
        raise RuntimeError("music cover job insert did not create or resolve a job")
    return job


async def _require_owner(session, user_uuid: str, content_hash: str) -> None:
    owner = (
        await session.execute(
            select(LocalImportOwner).where(
                LocalImportOwner.hash == content_hash,
                LocalImportOwner.user_uuid == user_uuid,
            )
        )
    ).scalar_one_or_none()
    if owner is None:
        raise AppError.forbidden("music cover requires local song ownership")


async def _cover_prompt(session, user_uuid: str, content_hash: str) -> str:
    item = (
        await session.execute(
            select(MusicPlaylistItem)
            .where(
                MusicPlaylistItem.user_uuid == user_uuid,
                MusicPlaylistItem.content_hash == content_hash,
            )
            .order_by(MusicPlaylistItem.added_at_ms.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    title = item.title_alias if item and item.title_alias else "Untitled track"
    artist = item.artist_alias if item and item.artist_alias else "Unknown artist"
    return (
        "Create premium 1:1 square album artwork, designed as a complete edge-to-edge cover. "
        f"Title concept: {title}. Artist concept: {artist}. "
        "Translate those concepts into mood and imagery only. Use one unmistakable visual subject "
        "occupying 70-80% of the canvas, with intentional foreground, midground, and background "
        "separation. Create a distinctive silhouette, expressive lighting, tactile detail, and a "
        "cohesive color story that remains recognizable at thumbnail size. Fill the entire canvas. "
        "No text, no letters, no typography, no vinyl record, no circular record label, no turntable, "
        "no UI elements, no mockup, no frame, no border, no watermark, no logo, no blank margins."
    )


def _job_response(job: MusicCoverJob) -> dict:
    return {
        "content_hash": job.content_hash,
        "job_id": job.id,
        "generation_epoch": job.generation_epoch,
        "status": job.status,
        "priority": job.priority,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "theme_color": job.theme_color,
        "cover_url": f"/api/music/covers/{job.content_hash}/file" if job.status == READY else None,
    }


def _suppressed_response(content_hash: str, epoch: int) -> dict:
    return {
        "content_hash": content_hash,
        "generation_epoch": epoch,
        "status": SUPPRESSED,
        "cover_url": None,
    }


def _require_local_profile() -> None:
    if get_settings().profile != Profile.LOCAL:
        raise AppError.bad_request(
            "local_music_cover_only", "music cover generation is available only in local profile"
        )


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
