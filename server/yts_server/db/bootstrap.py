from __future__ import annotations

from sqlalchemy import inspect, text

from .models import Base
from .session import get_engine


async def create_all_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_upgrade_music_schema)


def _upgrade_music_schema(connection) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
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
            text(
                "UPDATE music_playlist "
                "SET created_at_ms = updated_at_ms "
                "WHERE created_at_ms = 0"
            )
        )
    if "music_playlist_item" in table_names:
        _add_missing_columns(
            connection,
            "music_playlist_item",
            {
                "title_alias": "VARCHAR(255)",
                "artist_alias": "VARCHAR(255)",
            },
        )
    if {"music_playlist", "music_playlist_item"}.issubset(table_names):
        connection.execute(
            text(
                "UPDATE music_playlist "
                "SET item_count = ("
                "SELECT COUNT(*) FROM music_playlist_item "
                "WHERE music_playlist_item.playlist_id = music_playlist.id "
                "AND music_playlist_item.deleted_at_ms IS NULL"
                ")"
            )
        )


def _add_missing_columns(connection, table_name: str, columns: dict[str, str]) -> None:
    existing_columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
    for name, ddl in columns.items():
        if name not in existing_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}"))
