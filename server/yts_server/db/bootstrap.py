from __future__ import annotations

from sqlalchemy import inspect, text

from .models import Base
from .session import get_engine


async def create_all_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_validate_auth_schema)
        await conn.run_sync(_upgrade_music_schema)


def _upgrade_music_schema(connection) -> None:
    table_names = set(inspect(connection).get_table_names())
    if "music_playlist" in table_names:
        _add_missing_columns(
            connection,
            "music_playlist",
            {
                "scope": "VARCHAR(32) NOT NULL DEFAULT 'cloud'",
                "is_default": "BOOLEAN NOT NULL DEFAULT false",
                "item_count": "INTEGER NOT NULL DEFAULT 0",
                "created_at_ms": "BIGINT NOT NULL DEFAULT 0",
                "deleted_at_ms": "BIGINT",
                "op_clock": "BIGINT NOT NULL DEFAULT 0",
            },
        )
        connection.execute(
            text("UPDATE music_playlist SET created_at_ms = updated_at_ms WHERE created_at_ms = 0")
        )
    if "music_playlist_item" in table_names:
        _add_missing_columns(
            connection,
            "music_playlist_item",
            {"title_alias": "VARCHAR(255)", "artist_alias": "VARCHAR(255)"},
        )
        _upgrade_music_playlist_item_legacy_columns(connection)
        connection.execute(
            text(
                "UPDATE music_playlist_item SET title_alias = title "
                "WHERE title_alias IS NULL AND title IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE music_playlist_item SET artist_alias = artist "
                "WHERE artist_alias IS NULL AND artist IS NOT NULL"
            )
        )
    if {"music_playlist", "music_playlist_item"}.issubset(table_names):
        connection.execute(
            text(
                "UPDATE music_playlist SET item_count = ("
                "SELECT COUNT(*) FROM music_playlist_item "
                "WHERE music_playlist_item.playlist_id = music_playlist.id "
                "AND music_playlist_item.deleted_at_ms IS NULL)"
            )
        )
    if "music_cover_job" in table_names:
        _add_missing_columns(
            connection,
            "music_cover_job",
            {"theme_color": "VARCHAR(7)"},
        )


def _validate_auth_schema(connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("user_session")}
    required = {"device_id", "refresh_token_hash", "absolute_expires_at", "user_id"}
    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(
            "legacy authentication schema detected; run `alembic upgrade head` before startup; "
            f"missing columns: {', '.join(missing)}"
        )


def _add_missing_columns(connection, table_name: str, columns: dict[str, str]) -> None:
    existing_columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
    for name, ddl in columns.items():
        if name not in existing_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}"))


def _upgrade_music_playlist_item_legacy_columns(connection) -> None:
    if connection.dialect.name == "postgresql":
        columns = {
            column["name"]: column
            for column in inspect(connection).get_columns("music_playlist_item")
        }
        connection.execute(
            text("ALTER TABLE music_playlist_item ALTER COLUMN source DROP NOT NULL")
        )
        connection.execute(
            text("ALTER TABLE music_playlist_item ALTER COLUMN source_ref DROP NOT NULL")
        )
        position_type = str(columns["position"]["type"]).upper()
        if "INTEGER" not in position_type:
            connection.execute(
                text(
                    "ALTER TABLE music_playlist_item "
                    "ALTER COLUMN position TYPE INTEGER USING ROUND(position)::INTEGER"
                )
            )
