import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from .config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_FILENAME = "storymaker.db"


class MigrationError(RuntimeError):
    pass


def db_path() -> Path:
    return get_settings().data_dir / DB_FILENAME


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Each request gets its own connection, but FastAPI may create it on one
    # worker thread and use it on another, so the same-thread check is off.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Write-ahead logging: readers aren't blocked while a background job writes.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, closed afterwards."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply unapplied NNNN_<what>.sql files in number order, each in its own transaction.

    Migration files must not contain BEGIN or COMMIT; this function wraps each one.
    Returns the names of the migrations applied in this run.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}

    ran = []
    for path in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if path.name in applied:
            continue
        try:
            conn.executescript("BEGIN;\n" + path.read_text())
            conn.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (path.name, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            raise MigrationError(f"Migration {path.name} failed and was rolled back: {e}") from e
        ran.append(path.name)
    return ran
