import hashlib
import sqlite3

import pytest

from storymaker.db import connect
from storymaker.endpoints import trips
from storymaker.join_codes import ALPHABET

TRIP = "Goa 2026"
CREATOR = "Jean-Luc"


def create(client, trip_name=TRIP, display_name=CREATOR):
    return client.post("/api/trips", json={"trip_name": trip_name, "display_name": display_name})


def rows(table):
    with connect() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]


def test_creating_a_trip_returns_the_trip_its_creator_and_a_token(client):
    response = create(client)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"trip", "member", "token"}
    assert set(body["trip"]) == {"id", "name", "join_code", "status", "created_at"}
    assert set(body["member"]) == {"id", "display_name", "role", "joined_at"}
    assert body["trip"]["name"] == TRIP
    assert body["trip"]["status"] == "active"
    assert len(body["trip"]["join_code"]) == 6 and set(body["trip"]["join_code"]) <= set(ALPHABET)
    assert body["member"] == {**body["member"], "display_name": CREATOR, "role": "creator"}

    [trip], [member] = rows("trips"), rows("members")
    assert trip["id"] == body["trip"]["id"] and trip["status"] == "active"
    assert member["trip_id"] == trip["id"] and member["role"] == "creator"
    assert member["token_hash"] == hashlib.sha256(body["token"].encode()).hexdigest()
    stored = [value for row in (trip, member) for value in row.values()]
    assert body["token"] not in stored


def test_names_are_stored_exactly_as_typed(client):
    body = create(client, trip_name=" Coast road ", display_name=" Asha ").json()

    assert body["trip"]["name"] == " Coast road "
    assert body["member"]["display_name"] == " Asha "
    assert rows("members")[0]["display_name"] == " Asha "


@pytest.mark.parametrize(
    "name",
    ["Zoë", "O’Brien", "O'Brien", "J. R. Silva", "प्रिया", "محمد", "علی‌رضا", "ジョン・スミス", "张伟", "ʻIolani"],
)
def test_member_names_in_any_language_are_accepted(client, name):
    assert create(client, display_name=name).status_code == 201


@pytest.mark.parametrize("name", ["北海道の冬旅行2026", "Mia's 30th", "Rio ٢٠٢٦", "Coast road weekend"])
def test_trip_names_with_digits_are_accepted(client, name):
    assert create(client, trip_name=name).status_code == 201


@pytest.mark.parametrize(
    "field, name",
    [
        ("display_name", "Asha!!"),
        ("display_name", "DJ_K"),
        ("display_name", "Asha 2"),
        ("display_name", "🙂"),
        ("display_name", "@asha"),
        ("display_name", "   "),
        ("display_name", ""),
        ("display_name", "Ana " * 11),
        ("display_name", "a" * 61),
        ("trip_name", "Lisbon & Porto"),
        ("trip_name", "Road trip 🚗"),
        ("trip_name", "day " * 51),
        ("trip_name", "北" * 301),
    ],
)
def test_bad_names_are_refused_naming_the_field(client, field, name):
    response = create(client, **{field: name})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in error["message"]
    assert rows("trips") == []


def test_limits_are_inclusive(client):
    assert create(client, display_name="Ana " * 9 + "Ana").status_code == 201  # 10 words
    assert create(client, display_name="a" * 60).status_code == 201
    assert create(client, trip_name="北" * 300).status_code == 201


def test_two_trips_get_different_ids_codes_and_tokens(client):
    first, second = create(client).json(), create(client).json()

    assert first["trip"]["id"] != second["trip"]["id"]
    assert first["trip"]["join_code"] != second["trip"]["join_code"]
    assert first["token"] != second["token"]


def test_no_trip_is_left_behind_if_saving_the_creator_fails(client, monkeypatch):
    taken = create(client).json()["token"]
    # Reusing a token hash breaks the members table's UNIQUE rule (02.1) on the second insert.
    monkeypatch.setattr(trips, "new_token", lambda: (taken, hashlib.sha256(taken.encode()).hexdigest()))

    with pytest.raises(sqlite3.IntegrityError):
        create(client, trip_name="Second trip")
    assert [trip["name"] for trip in rows("trips")] == [TRIP]
