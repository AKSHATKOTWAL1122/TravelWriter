import hashlib
import sqlite3

import pytest

from storymaker.db import connect
from storymaker.ids import new_id
from storymaker.times import utc_now_iso


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def ask_to_rejoin(client, join_code, display_name):
    return client.post("/api/trips/rejoin", json={"join_code": join_code, "display_name": display_name})


def requests_of(member_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, token_hash, status, created_at, closed_at FROM rejoin_requests WHERE member_id = ? ORDER BY rowid",
            (member_id,),
        )
        return [dict(row) for row in rows]


@pytest.fixture
def trip(client):
    """A trip with its creator and one friend, each with their phone's token."""
    created = client.post("/api/trips", json={"trip_name": "Hokkaido ski week", "display_name": "Mariana"}).json()
    joined = client.post("/api/trips/join", json={"join_code": created["trip"]["join_code"], "display_name": "Yusuf"}).json()
    return {"trip": created["trip"], "creator": created, "friend": joined}


def test_asking_gives_a_pending_request_and_a_token_that_waits(client, trip):
    code = trip["trip"]["join_code"]

    response = ask_to_rejoin(client, f"{code[:3].lower()}-{code[3:].lower()}", "yusuf ")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"request", "trip", "member", "token"}
    assert set(body["request"]) == {"id", "status", "created_at"} and body["request"]["status"] == "pending"
    assert body["trip"] == trip["trip"]
    assert body["member"] == trip["friend"]["member"]  # the existing member, name as stored
    [stored] = requests_of(body["member"]["id"])
    assert stored["id"] == body["request"]["id"]
    assert stored["token_hash"] == hashlib.sha256(body["token"].encode()).hexdigest()
    assert body["token"] not in stored.values()
    trip_url = f"/api/trips/{trip['trip']['id']}"
    assert client.get(trip_url, headers=bearer(body["token"])).json()["error"]["code"] == "token_invalid"
    assert client.get(trip_url, headers=bearer(trip["friend"]["token"])).status_code == 200  # old phone still works


def test_unknown_codes_and_names_are_turned_away(client, trip):
    code = trip["trip"]["join_code"]
    unknown = "ZZZZZZ" if code != "ZZZZZZ" else "YYYYYY"

    for typed in (unknown, "K0MPQ4", ""):
        response = ask_to_rejoin(client, typed, "Yusuf")
        assert response.status_code == 404 and response.json()["error"]["code"] == "trip_not_found"
    client.post("/api/trips", json={"trip_name": "Lake Malawi kayaking", "display_name": "Kofi"})
    response = ask_to_rejoin(client, code, "Kofi")  # only in another trip
    assert response.status_code == 404 and response.json()["error"]["code"] == "member_not_found"
    response = ask_to_rejoin(client, code, "Yusuf 2")
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"


def test_asking_again_replaces_the_pending_request(client, trip):
    code, friend_id = trip["trip"]["join_code"], trip["friend"]["member"]["id"]

    first = ask_to_rejoin(client, code, "Yusuf").json()
    second = ask_to_rejoin(client, code, "Yusuf").json()
    ask_to_rejoin(client, code, "Mariana")  # another member's request is separate

    older, newer = requests_of(friend_id)
    assert (older["id"], older["status"]) == (first["request"]["id"], "replaced")
    assert older["closed_at"] == second["request"]["created_at"]
    assert (newer["id"], newer["status"], newer["closed_at"]) == (second["request"]["id"], "pending", None)
    assert [r["status"] for r in requests_of(trip["creator"]["member"]["id"])] == ["pending"]
    for token in (first["token"], second["token"]):
        assert client.get(f"/api/trips/{trip['trip']['id']}", headers=bearer(token)).status_code == 401


def test_the_creator_can_ask_also_in_an_ended_trip(client, trip):
    with connect() as conn:
        conn.execute("UPDATE trips SET status = 'ended', ended_at = ? WHERE id = ?", (utc_now_iso(), trip["trip"]["id"]))

    response = ask_to_rejoin(client, trip["trip"]["join_code"], "MARIANA")

    assert response.status_code == 201
    body = response.json()
    assert body["member"] == trip["creator"]["member"] and body["member"]["role"] == "creator"
    assert body["trip"]["status"] == "ended"


def insert_request(conn, member_id, *, status="pending", closed_at=None):
    conn.execute(
        "INSERT INTO rejoin_requests (id, member_id, token_hash, status, created_at, closed_at) VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), member_id, new_id(), status, utc_now_iso(), closed_at),
    )


@pytest.mark.parametrize(
    "status, closed_at",
    [
        ("pending", None),  # a second pending request for the same member
        ("cancelled", utc_now_iso()),  # not a status
        ("replaced", None),  # closed, but no closed_at
    ],
)
def test_the_database_guards_the_request_rules(client, trip, status, closed_at):
    friend_id = trip["friend"]["member"]["id"]
    with connect() as conn:
        insert_request(conn, friend_id)
        with pytest.raises(sqlite3.IntegrityError):
            insert_request(conn, friend_id, status=status, closed_at=closed_at)


def test_a_pending_request_cannot_have_closed_at(client, trip):
    with connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_request(conn, trip["friend"]["member"]["id"], closed_at=utc_now_iso())
