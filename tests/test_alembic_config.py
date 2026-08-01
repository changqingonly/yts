from pathlib import Path


def test_alembic_script_location_is_relative_to_config_file() -> None:
    config = (Path(__file__).parents[1] / "server" / "alembic.ini").read_text(encoding="utf-8")

    assert "script_location = %(here)s/yts_server/alembic" in config
