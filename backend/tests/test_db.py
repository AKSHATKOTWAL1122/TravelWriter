import re
import sqlite3

import pytest

from storymaker.config import BACKEND_DIR, get_settings
from storymaker.db import MigrationError, connect, db_path, run_migrations


def write(folder, name, sql):
    (folder / name).write_text(sql)


def test_app_startup_creates_the_database(client):
    assert db_path().exists()
    with connect() as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "schema_migrations" in tables
    assert client.get("/health").json() == {"status": "ok"}


def test_migrations_run_in_number_order_and_only_once(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    # 0002 only works if 0001 ran first.
    write(migrations, "0002_add_row.sql", "INSERT INTO places (id) VALUES ('p1');")
    write(migrations, "0001_create_places.sql", "CREATE TABLE places (id TEXT PRIMARY KEY);")
    conn = connect()

    assert run_migrations(conn, migrations) == ["0001_create_places.sql", "0002_add_row.sql"]
    recorded = [row["name"] for row in conn.execute("SELECT name FROM schema_migrations ORDER BY name")]
    assert recorded == ["0001_create_places.sql", "0002_add_row.sql"]

    assert run_migrations(conn, migrations) == []
    assert conn.execute("SELECT COUNT(*) FROM places").fetchone()[0] == 1


def test_applied_at_uses_the_shared_time_format(tmp_path):
    # ISSUE-045: same format as the API (spec 01.4), so text order = time order.
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    write(migrations, "0001_create_places.sql", "CREATE TABLE places (id TEXT PRIMARY KEY);")
    conn = connect()
    run_migrations(conn, migrations)

    applied_at = conn.execute("SELECT applied_at FROM schema_migrations").fetchone()["applied_at"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", applied_at)


def test_broken_migration_is_rolled_back_and_named(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    write(migrations, "0001_good.sql", "CREATE TABLE good (id TEXT PRIMARY KEY);")
    write(migrations, "0002_bad.sql", "CREATE TABLE half_done (id TEXT);\nINSERT INTO missing_table VALUES (1);")
    conn = connect()

    with pytest.raises(MigrationError, match="0002_bad.sql"):
        run_migrations(conn, migrations)

    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "good" in tables
    assert "half_done" not in tables  # no partial changes
    assert [row["name"] for row in conn.execute("SELECT name FROM schema_migrations")] == ["0001_good.sql"]


def test_foreign_keys_are_enforced():
    conn = connect()
    conn.execute("CREATE TABLE parent (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE child (id TEXT PRIMARY KEY, parent_id TEXT NOT NULL REFERENCES parent(id))")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO child (id, parent_id) VALUES ('c1', 'no-such-parent')")


def test_connections_use_wal_and_named_columns():
    conn = connect()

    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("SELECT 1 AS answer").fetchone()["answer"] == 1


def test_each_test_uses_a_temporary_data_folder(tmp_path):
    data_dir = get_settings().data_dir

    assert data_dir == tmp_path / "data"
    assert data_dir != BACKEND_DIR / "data"
