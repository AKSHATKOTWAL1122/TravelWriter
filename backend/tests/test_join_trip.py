import hashlib

import pytest

from storymaker.auth import current_member
from storymaker.db import connect
from storymaker.endpoints import join
from storymaker.times import utc_now_iso


def create_trip(client, trip_name="Patagonia by car", creator="Asha"):
    body = client.post("/api/trips", json={"trip_name": trip_name, "display_name": creator}).json()
    return body["trip"]


def join_trip(client, join_code, display_name):
    return client.post("/api/trips/join", json={"join_code": join_code, "display_name": display_name})


def member_names(trip_id):
    with connect() as conn:
        return [row["display_name"] for row in conn.execute("SELECT display_name FROM members WHERE trip_id = ?", (trip_id,))]


def test_joining_gives_a_member_and_a_working_token(client):
    trip = create_trip(client)

    response = join_trip(client, trip["join_code"], "Tomás")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"trip", "member", "token"}
    assert body["trip"] == trip
    assert set(body["member"]) == {"id", "display_name", "role", "joined_at"}
    assert body["member"]["display_name"] == "Tomás" and body["member"]["role"] == "member"
    with connect() as conn:
        stored_hash = conn.execute("SELECT token_hash FROM members WHERE id = ?", (body["member"]["id"],)).fetchone()[0]
        signed_in = current_member(conn, f"Bearer {body['token']}")  # 02.4
    assert stored_hash == hashlib.sha256(body["token"].encode()).hexdigest()
    assert (signed_in.id, signed_in.trip_id, signed_in.role) == (body["member"]["id"], trip["id"], "member")


def test_the_code_can_be_typed_loosely(client):
    code = create_trip(client)["join_code"]

    assert join_trip(client, f"{code[:3].lower()} {code[3:].lower()}", "Tomás").status_code == 201
    assert join_trip(client, f" {code[:3]}-{code[3:]} ", "Ines").status_code == 201


def test_unknown_or_impossible_codes_are_trip_not_found(client):
    code = create_trip(client)["join_code"]
    unknown = "ZZZZZZ" if code != "ZZZZZZ" else "YYYYYY"

    for typed in (unknown, "K0MPQ4", ""):
        response = join_trip(client, typed, "Tomás")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "trip_not_found"


def test_a_name_already_in_the_trip_is_taken(client):
    trip = create_trip(client, creator="Asha")
    other = create_trip(client, trip_name="Lagos weekend", creator="Bo")

    response = join_trip(client, trip["join_code"], "asha ")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "name_taken"
    assert member_names(trip["id"]) == ["Asha"]
    assert join_trip(client, other["join_code"], "Asha").status_code == 201  # fine in another trip


def test_a_name_taken_between_check_and_save_is_still_name_taken(client, monkeypatch):
    trip = create_trip(client, creator="Asha")
    monkeypatch.setattr(join, "_name_in_use", lambda *args: False)  # the check misses it, as in a race

    response = join_trip(client, trip["join_code"], "ASHA")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "name_taken"
    assert member_names(trip["id"]) == ["Asha"]


def test_the_name_rules_from_02_3_apply(client):
    code = create_trip(client)["join_code"]

    response = join_trip(client, code, "Asha 2")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_an_ended_trip_can_still_be_joined(client):
    trip = create_trip(client)
    with connect() as conn:
        conn.execute("UPDATE trips SET status = 'ended', ended_at = ? WHERE id = ?", (utc_now_iso(), trip["id"]))

    response = join_trip(client, trip["join_code"], "Tomás")

    assert response.status_code == 201
    assert response.json()["trip"]["status"] == "ended"


@pytest.mark.parametrize("body", [{"display_name": "Tomás"}, {"join_code": "K7MPQ4"}])
def test_missing_fields_are_validation_errors(client, body):
    assert client.post("/api/trips/join", json=body).json()["error"]["code"] == "validation_error"
