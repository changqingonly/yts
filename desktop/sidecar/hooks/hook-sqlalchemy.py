"""PyInstaller hook for the SQLite-only macOS sidecar."""

excludedimports = ["sqlalchemy.testing"]

hiddenimports = [
    "sqlalchemy.dialects.sqlite.aiosqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "sqlalchemy.ext.baked",
    "sqlalchemy.sql.default_comparator",
]
