import sqlite3

import pytest

from storymaker.db import connect, run_migrations
from storymaker.ids import new_id
from storymaker.names import name_key
from storymaker.times import utc_now_iso


@pytest.fixture
def conn():
    conn = connect()
    run_migrations(conn)
    yield conn
    conn.close()


def add_trip(conn, *, join_code=None, status="active", ended_at=None) -> str:
    trip_id = new_id()
    conn.execute(
        "INSERT INTO trips (id, name, join_code, status, created_at, ended_at) VALUES (?, ?, ?, ?, ?, ?)",
        (trip_id, "Coast road weekend", join_code or new_id()[:6], status, utc_now_iso(), ended_at),
    )
    return trip_id


def add_member(conn, trip_id, name, *, role="member", token_hash=None) -> str:
    member_id = new_id()
    conn.execute(
        "INSERT INTO members (id, trip_id, display_name, name_key, role, token_hash, joined_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (member_id, trip_id, name, name_key(name), role, token_hash or new_id(), utc_now_iso()),
    )
    return member_id


def test_startup_applies_the_migration_once(client):
    with connect() as c:
        applied = [r["name"] for r in c.execute("SELECT name FROM schema_migrations")]
        tables = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert run_migrations(c) == []  # a restart runs nothing
    assert "0001_trips_and_members.sql" in applied
    assert {"trips", "members"} <= tables


def test_invalid_status_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_trip(conn, status="paused")


def test_invalid_role_is_rejected(conn):
    trip_id = add_trip(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_member(conn, trip_id, "Asha", role="admin")


def test_a_trip_cannot_have_two_creators(conn):
    trip_id = add_trip(conn)
    add_member(conn, trip_id, "Asha", role="creator")
    with pytest.raises(sqlite3.IntegrityError):
        add_member(conn, trip_id, "Bilal", role="creator")


def test_duplicate_join_codes_are_rejected(conn):
    add_trip(conn, join_code="K7Q2MX")
    with pytest.raises(sqlite3.IntegrityError):
        add_trip(conn, join_code="K7Q2MX")


def test_duplicate_token_hashes_are_rejected(conn):
    trip_id = add_trip(conn)
    add_member(conn, trip_id, "Asha", token_hash="same-hash")
    with pytest.raises(sqlite3.IntegrityError):
        add_member(conn, trip_id, "Bilal", token_hash="same-hash")


def test_member_must_belong_to_a_real_trip(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_member(conn, "no-such-trip", "Asha")


def test_ended_at_only_with_ended_status(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_trip(conn, status="active", ended_at=utc_now_iso())
    with pytest.raises(sqlite3.IntegrityError):
        add_trip(conn, status="ended", ended_at=None)
    add_trip(conn, status="ended", ended_at=utc_now_iso())  # the valid combination works


@pytest.mark.parametrize(("first", "second"), [("Asha", "asha"), ("Zoë", "ZOË"), ("Asha", "  Asha  "), ("Ölen", "ölen")])
def test_names_are_unique_per_trip_ignoring_case(conn, first, second):
    trip_id = add_trip(conn)
    add_member(conn, trip_id, first)
    with pytest.raises(sqlite3.IntegrityError):
        add_member(conn, trip_id, second)


def test_same_name_in_different_trips_is_fine(conn):
    add_member(conn, add_trip(conn), "Asha")
    add_member(conn, add_trip(conn), "Asha")


def test_name_key_works_beyond_english():
    assert name_key("Zoë") == name_key("ZOË")
    assert name_key("  Asha   Rao ") == name_key("asha rao")
    assert name_key("मीरा") == name_key(" मीरा ")  # scripts without case still compare cleanly
    assert name_key("Asha") != name_key("Asha R")
