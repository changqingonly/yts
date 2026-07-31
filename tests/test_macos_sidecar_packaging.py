from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "desktop" / "sidecar" / "build_macos.spec"
SQLALCHEMY_HOOK = ROOT / "desktop" / "sidecar" / "hooks" / "hook-sqlalchemy.py"


def test_macos_sidecar_uses_local_sqlalchemy_hook_for_sqlite_only() -> None:
    spec_source = SPEC.read_text(encoding="utf-8")
    hook_source = SQLALCHEMY_HOOK.read_text(encoding="utf-8")

    assert "hookspath=['desktop/sidecar/hooks']" in spec_source
    assert '"sqlalchemy.dialects.sqlite.aiosqlite"' in hook_source
    assert '"sqlalchemy.dialects.sqlite.pysqlite"' in hook_source

    unused_drivers = ("pysqlite2", "MySQLdb", "psycopg2")
    assert all(driver not in hook_source for driver in unused_drivers)
