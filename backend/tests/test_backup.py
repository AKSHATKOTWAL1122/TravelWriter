import sqlite3
from typing import Annotated

import pytest
from fastapi import Depends

from storymaker.auth import CurrentMember, current_member, trip_member
from storymaker.db import connect
from storymaker.endpoints import rejoin
from storymaker.times import utc_now_iso
from storymaker.tokens import new_token


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def trip(client):
    """Mei creates a trip; Kofi and Lucía join, each with their phone's token."""
    created = client.post("/api/trips", json={"trip_name": "Kerala backwaters", "display_name": "Mei"}).json()
    code = created["trip"]["join_code"]
    kofi = client.post("/api/trips/join", json={"join_code": code, "display_name": "Kofi"}).json()
    lucia = client.post("/api/trips/join", json={"join_code": code, "display_name": "Lucía"}).json()
    return {"trip": created["trip"], "mei": created, "kofi": kofi, "lucia": lucia}


def trip_url(trip):
    return f"/api/trips/{trip['trip']['id']}"


def pick(client, trip, phone, backup_member_id):
    return client.put(f"{trip_url(trip)}/backup", json={"backup_member_id": backup_member_id}, headers=bearer(trip[phone]["token"]))


def backup_seen_by(client, trip, phone):
    response = client.get(trip_url(trip), headers=bearer(trip[phone]["token"]))
    assert response.status_code == 200
    return response.json()["backup_member_id"]


def member_id(trip, phone):
    return trip[phone]["member"]["id"]


def ask_to_rejoin(client, trip, display_name):
    response = client.post("/api/trips/rejoin", json={"join_code": trip["trip"]["join_code"], "display_name": display_name})
    assert response.status_code == 201
    return response.json()


def listed(client, trip, token):
    response = client.get(f"{trip_url(trip)}/rejoin-requests", headers=bearer(token))
    assert response.status_code == 200
    return [r["id"] for r in response.json()["requests"]]


def decide(client, trip, request_id, token, decision):
    return client.post(f"{trip_url(trip)}/rejoin-requests/{request_id}/{decision}", headers=bearer(token))


def error_code(response):
    return response.json()["error"]["code"]


def test_the_creator_picks_moves_and_clears_the_backup(client, trip):
    phones = ("mei", "kofi", "lucia")
    assert [backup_seen_by(client, trip, phone) for phone in phones] == [None, None, None]

    response = pick(client, trip, "mei", member_id(trip, "kofi"))
    assert response.status_code == 200
    assert response.json() == {"backup_member_id": member_id(trip, "kofi")}
    assert [backup_seen_by(client, trip, phone) for phone in phones] == [member_id(trip, "kofi")] * 3

    assert pick(client, trip, "mei", member_id(trip, "lucia")).json() == {"backup_member_id": member_id(trip, "lucia")}
    assert backup_seen_by(client, trip, "kofi") == member_id(trip, "lucia")

    assert pick(client, trip, "mei", None).json() == {"backup_member_id": None}
    assert backup_seen_by(client, trip, "lucia") is None


def test_the_backup_approves_the_creators_request_at_once(client, trip):
    pick(client, trip, "mei", member_id(trip, "kofi"))
    asked = ask_to_rejoin(client, trip, "Mei")

    assert listed(client, trip, trip["kofi"]["token"]) == [asked["request"]["id"]]
    assert listed(client, trip, trip["mei"]["token"]) == []  # her old phone
    assert listed(client, trip, trip["lucia"]["token"]) == []

    response = decide(client, trip, asked["request"]["id"], trip["kofi"]["token"], "approve")
    assert response.status_code == 200
    assert response.json() == {"request": {**asked["request"], "status": "approved"}}

    loaded = client.get(trip_url(trip), headers=bearer(asked["token"]))
    assert loaded.status_code == 200
    [mei] = [m for m in loaded.json()["members"] if m["display_name"] == "Mei"]
    assert mei == trip["mei"]["member"]  # same ID, still the creator
    assert loaded.json()["backup_member_id"] == member_id(trip, "kofi")
    old = client.get(trip_url(trip), headers=bearer(trip["mei"]["token"]))
    assert old.status_code == 401 and error_code(old) == "token_invalid"
    # The new phone has the creator's powers, the old one none.
    assert pick(client, trip, "mei", None).status_code == 401
    assert client.put(f"{trip_url(trip)}/backup", json={"backup_member_id": None}, headers=bearer(asked["token"])).status_code == 200


def test_the_backup_declining_keeps_the_creators_old_login(client, trip):
    pick(client, trip, "mei", member_id(trip, "kofi"))
    asked = ask_to_rejoin(client, trip, "Mei")

    response = decide(client, trip, asked["request"]["id"], trip["kofi"]["token"], "decline")

    assert response.status_code == 200 and response.json()["request"]["status"] == "declined"
    assert backup_seen_by(client, trip, "mei") == member_id(trip, "kofi")  # her old phone still works
    assert error_code(client.get(trip_url(trip), headers=bearer(asked["token"]))) == "token_invalid"


@pytest.mark.parametrize("decision", ["approve", "decline"])
def test_only_the_current_backup_decides_the_creators_request(client, trip, decision):
    pick(client, trip, "mei", member_id(trip, "kofi"))
    asked = ask_to_rejoin(client, trip, "Mei")
    request_id = asked["request"]["id"]

    for phone in ("mei", "lucia"):
        response = decide(client, trip, request_id, trip[phone]["token"], decision)
        assert response.status_code == 403 and error_code(response) == "not_allowed"
        assert "backup" in response.json()["error"]["message"]

    pick(client, trip, "mei", member_id(trip, "lucia"))  # picked after the request was made
    assert listed(client, trip, trip["kofi"]["token"]) == []
    response = decide(client, trip, request_id, trip["kofi"]["token"], decision)
    assert response.status_code == 403 and error_code(response) == "not_allowed"
    assert listed(client, trip, trip["lucia"]["token"]) == [request_id]
    assert decide(client, trip, request_id, trip["lucia"]["token"], decision).status_code == 200


def test_with_no_backup_nobody_decides_the_creators_request(client, trip):
    pick(client, trip, "mei", member_id(trip, "kofi"))
    pick(client, trip, "mei", None)
    asked = ask_to_rejoin(client, trip, "Mei")

    for phone in ("mei", "kofi", "lucia"):
        assert listed(client, trip, trip[phone]["token"]) == []
        response = decide(client, trip, asked["request"]["id"], trip[phone]["token"], "approve")
        assert response.status_code == 403 and error_code(response) == "not_allowed"
        assert "no backup" in response.json()["error"]["message"]


@pytest.mark.parametrize("decision", ["approve", "decline"])
def test_a_backup_switched_between_the_check_and_the_save_decides_nothing(client, trip, monkeypatch, decision):
    pick(client, trip, "mei", member_id(trip, "kofi"))
    asked = ask_to_rejoin(client, trip, "Mei")
    may_decide = rejoin._may_decide

    def mei_moves_the_backup_first(*args):
        with connect() as conn:  # what Mei picking Lucía does
            conn.execute("UPDATE members SET is_backup = 0 WHERE id = ?", (member_id(trip, "kofi"),))
            conn.execute("UPDATE members SET is_backup = 1 WHERE id = ?", (member_id(trip, "lucia"),))
        return may_decide(*args)

    monkeypatch.setattr(rejoin, "_may_decide", mei_moves_the_backup_first)
    response = decide(client, trip, asked["request"]["id"], trip["kofi"]["token"], decision)
    monkeypatch.undo()

    assert response.status_code == 403 and error_code(response) == "not_allowed"
    assert "backup" in response.json()["error"]["message"]
    assert listed(client, trip, trip["lucia"]["token"]) == [asked["request"]["id"]]  # still pending, now hers
    assert backup_seen_by(client, trip, "mei") == member_id(trip, "lucia")  # Mei's old login still works
    assert error_code(client.get(trip_url(trip), headers=bearer(asked["token"]))) == "token_invalid"


@pytest.mark.parametrize("phone", ["lucia", None])
def test_a_login_moved_between_the_check_and_the_save_picks_nothing(client, trip, monkeypatch, phone):
    pick(client, trip, "mei", member_id(trip, "kofi"))
    _, new_hash = new_token()

    def checked_then_moved(trip_id: str, member: Annotated[CurrentMember, Depends(current_member)]) -> CurrentMember:
        checked = trip_member(trip_id, member)
        with connect() as conn:  # Mei's rejoin is approved in that instant
            conn.execute("UPDATE members SET token_hash = ? WHERE id = ?", (new_hash, member_id(trip, "mei")))
        return checked

    monkeypatch.setitem(client.app.dependency_overrides, trip_member, checked_then_moved)
    response = pick(client, trip, "mei", member_id(trip, phone) if phone else None)
    monkeypatch.undo()

    assert response.status_code == 401 and error_code(response) == "token_invalid"
    assert backup_seen_by(client, trip, "kofi") == member_id(trip, "kofi")


def test_the_backup_gets_no_say_over_members_requests(client, trip):
    pick(client, trip, "mei", member_id(trip, "kofi"))
    asked = ask_to_rejoin(client, trip, "Lucía")

    assert listed(client, trip, trip["kofi"]["token"]) == []
    response = decide(client, trip, asked["request"]["id"], trip["kofi"]["token"], "approve")
    assert response.status_code == 403 and error_code(response) == "not_allowed"
    assert listed(client, trip, trip["mei"]["token"]) == [asked["request"]["id"]]
    assert decide(client, trip, asked["request"]["id"], trip["mei"]["token"], "approve").status_code == 200


def test_a_backup_who_rejoins_is_still_the_backup(client, trip):
    pick(client, trip, "mei", member_id(trip, "kofi"))
    asked = ask_to_rejoin(client, trip, "Kofi")
    decide(client, trip, asked["request"]["id"], trip["mei"]["token"], "approve")

    assert backup_seen_by(client, trip, "mei") == member_id(trip, "kofi")
    creators = ask_to_rejoin(client, trip, "Mei")
    assert listed(client, trip, asked["token"]) == [creators["request"]["id"]]  # Kofi's new phone


def test_bad_picks_are_refused_and_change_nothing(client, trip):
    other = client.post("/api/trips", json={"trip_name": "Lapland northern lights", "display_name": "Aino"}).json()
    pick(client, trip, "mei", member_id(trip, "kofi"))
    url = f"{trip_url(trip)}/backup"

    for phone in ("kofi", "lucia"):
        response = pick(client, trip, phone, member_id(trip, "lucia"))
        assert response.status_code == 403 and error_code(response) == "creator_only"
    response = pick(client, trip, "mei", member_id(trip, "mei"))
    assert response.status_code == 422 and error_code(response) == "validation_error"
    assert "backup_member_id" in response.json()["error"]["message"]
    response = client.put(url, json={}, headers=bearer(trip["mei"]["token"]))
    assert response.status_code == 422 and "backup_member_id" in response.json()["error"]["message"]
    for made_up in ("made-up-id", other["member"]["id"]):
        response = pick(client, trip, "mei", made_up)
        assert response.status_code == 404 and error_code(response) == "member_not_found"

    assert backup_seen_by(client, trip, "mei") == member_id(trip, "kofi")
    assert error_code(client.put(url, json={"backup_member_id": None})) == "token_missing"
    response = client.put(url, json={"backup_member_id": None}, headers=bearer(other["token"]))
    assert error_code(response) == "not_a_member"


def test_picking_works_in_an_ended_trip(client, trip):
    with connect() as conn:
        conn.execute("UPDATE trips SET status = 'ended', ended_at = ? WHERE id = ?", (utc_now_iso(), trip["trip"]["id"]))

    assert pick(client, trip, "mei", member_id(trip, "lucia")).status_code == 200
    assert backup_seen_by(client, trip, "kofi") == member_id(trip, "lucia")


def test_the_database_allows_one_backup_per_trip_and_never_the_creator(client, trip):
    set_backup = "UPDATE members SET is_backup = ? WHERE id = ?"
    with connect() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(set_backup, (1, member_id(trip, "mei")))
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(set_backup, (2, member_id(trip, "lucia")))
        conn.execute(set_backup, (1, member_id(trip, "kofi")))
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            conn.execute(set_backup, (1, member_id(trip, "lucia")))
