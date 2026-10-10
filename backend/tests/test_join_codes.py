import pytest

from storymaker import join_codes
from storymaker.db import connect, run_migrations
from storymaker.ids import new_id
from storymaker.join_codes import ALPHABET, new_join_code, normalize_join_code
from storymaker.times import utc_now_iso


@pytest.fixture
def conn():
    conn = connect()
    run_migrations(conn)
    yield conn
    conn.close()


def add_trip(conn, join_code, *, status="active", ended_at=None):
    conn.execute(
        "INSERT INTO trips (id, name, join_code, status, created_at, ended_at) VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), "Fjords by train", join_code, status, utc_now_iso(), ended_at),
    )


def test_alphabet_is_31_symbols_without_look_alikes():
    assert len(ALPHABET) == len(set(ALPHABET)) == 31
    assert not set("OIL01") & set(ALPHABET)


def test_new_codes_are_six_characters_from_the_alphabet(conn):
    codes = [new_join_code(conn) for _ in range(10_000)]

    assert all(len(code) == 6 and set(code) <= set(ALPHABET) for code in codes)


def test_a_code_used_by_another_trip_is_skipped_even_if_that_trip_ended(conn, monkeypatch):
    add_trip(conn, "K7MPQ4", status="ended", ended_at=utc_now_iso())
    picks = iter(["K7MPQ4", "R2D2XY"])
    monkeypatch.setattr(join_codes, "_random_code", lambda: next(picks))

    assert new_join_code(conn) == "R2D2XY"


def test_gives_up_after_ten_taken_picks(conn, monkeypatch):
    add_trip(conn, "K7MPQ4")
    calls = []
    monkeypatch.setattr(join_codes, "_random_code", lambda: calls.append(1) or "K7MPQ4")

    with pytest.raises(RuntimeError, match="10 tries"):
        new_join_code(conn)
    assert len(calls) == 10


@pytest.mark.parametrize("typed", ["k7m pq4", "K7M-PQ4", " k7m–pq4 ", "Ｋ７ＭＰＱ４", "K7MPQ4"])
def test_typed_codes_are_normalized(typed):
    assert normalize_join_code(typed) == "K7MPQ4"


@pytest.mark.parametrize("typed", ["K7MPQ", "K7MPQ44", "K0MPQ4", "K7M?Q4", ""])
def test_impossible_codes_are_rejected(typed):
    with pytest.raises(ValueError):
        normalize_join_code(typed)
