import pytest

from storymaker.db import connect
from storymaker.endpoints import rejoin
from storymaker.times import utc_now_iso


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def trip(client):
    """A trip with its creator and two friends, each with their phone's token."""
    created = client.post("/api/trips", json={"trip_name": "Patagonia trek", "display_name": "Ingrid"}).json()
    code = created["trip"]["join_code"]
    yusuf = client.post("/api/trips/join", json={"join_code": code, "display_name": "Yusuf"}).json()
    chidi = client.post("/api/trips/join", json={"join_code": code, "display_name": "Chidi"}).json()
    return {"trip": created["trip"], "creator": created, "yusuf": yusuf, "chidi": chidi}


def ask_to_rejoin(client, trip, display_name):
    response = client.post("/api/trips/rejoin", json={"join_code": trip["trip"]["join_code"], "display_name": display_name})
    assert response.status_code == 201
    return response.json()


def requests_url(trip):
    return f"/api/trips/{trip['trip']['id']}/rejoin-requests"


def listed(client, trip, token):
    response = client.get(requests_url(trip), headers=bearer(token))
    assert response.status_code == 200
    return response.json()["requests"]


def decide(client, trip, request_id, token, decision):
    return client.post(f"{requests_url(trip)}/{request_id}/{decision}", headers=bearer(token))


def get_trip(client, trip, token):
    return client.get(f"/api/trips/{trip['trip']['id']}", headers=bearer(token))


def error_code(response):
    return response.json()["error"]["code"]


def test_the_creator_sees_a_members_request_and_nobody_else_does(client, trip):
    asked = ask_to_rejoin(client, trip, "Yusuf")

    [request] = listed(client, trip, trip["creator"]["token"])
    assert request == {**asked["request"], "member": trip["yusuf"]["member"]}
    assert listed(client, trip, trip["yusuf"]["token"]) == []  # Yusuf's old phone
    assert listed(client, trip, trip["chidi"]["token"]) == []


def test_requests_are_listed_oldest_first(client, trip):
    first = ask_to_rejoin(client, trip, "Chidi")["request"]
    second = ask_to_rejoin(client, trip, "Yusuf")["request"]

    assert [r["id"] for r in listed(client, trip, trip["creator"]["token"])] == [first["id"], second["id"]]


def test_approving_moves_the_login_to_the_new_phone(client, trip):
    asked = ask_to_rejoin(client, trip, "Yusuf")

    response = decide(client, trip, asked["request"]["id"], trip["creator"]["token"], "approve")

    assert response.status_code == 200
    assert response.json() == {"request": {**asked["request"], "status": "approved"}}
    loaded = get_trip(client, trip, asked["token"])
    assert loaded.status_code == 200
    [yusuf] = [m for m in loaded.json()["members"] if m["display_name"] == "Yusuf"]
    assert yusuf == trip["yusuf"]["member"]  # same ID, name, role and joined_at
    assert error_code(get_trip(client, trip, trip["yusuf"]["token"])) == "token_invalid"
    assert listed(client, trip, trip["creator"]["token"]) == []
    with connect() as conn:
        closed_at = conn.execute("SELECT closed_at FROM rejoin_requests WHERE id = ?", (asked["request"]["id"],)).fetchone()[0]
    assert closed_at is not None


def test_declining_keeps_the_old_login(client, trip):
    asked = ask_to_rejoin(client, trip, "Yusuf")

    response = decide(client, trip, asked["request"]["id"], trip["creator"]["token"], "decline")

    assert response.status_code == 200
    assert response.json() == {"request": {**asked["request"], "status": "declined"}}
    assert error_code(get_trip(client, trip, asked["token"])) == "token_invalid"
    assert get_trip(client, trip, trip["yusuf"]["token"]).status_code == 200
    assert listed(client, trip, trip["creator"]["token"]) == []


@pytest.mark.parametrize("decision", ["approve", "decline"])
def test_only_the_creator_decides_a_members_request(client, trip, decision):
    asked = ask_to_rejoin(client, trip, "Yusuf")

    for phone in ("chidi", "yusuf"):  # a friend, and Yusuf's own old phone
        response = decide(client, trip, asked["request"]["id"], trip[phone]["token"], decision)
        assert response.status_code == 403 and error_code(response) == "not_allowed"
    assert listed(client, trip, trip["creator"]["token"])[0]["status"] == "pending"


@pytest.mark.parametrize("decision", ["approve", "decline"])
def test_with_no_backup_nobody_decides_the_creators_own_request(client, trip, decision):
    asked = ask_to_rejoin(client, trip, "Ingrid")

    for phone in ("creator", "yusuf", "chidi"):
        assert listed(client, trip, trip[phone]["token"]) == []
        response = decide(client, trip, asked["request"]["id"], trip[phone]["token"], decision)
        assert response.status_code == 403 and error_code(response) == "not_allowed"
    assert get_trip(client, trip, trip["creator"]["token"]).status_code == 200


def test_a_closed_request_cannot_be_decided(client, trip):
    first = ask_to_rejoin(client, trip, "Yusuf")
    second = ask_to_rejoin(client, trip, "Yusuf")  # replaces the first
    creator = trip["creator"]["token"]

    response = decide(client, trip, first["request"]["id"], creator, "approve")
    assert response.status_code == 409 and error_code(response) == "request_closed"
    assert decide(client, trip, second["request"]["id"], creator, "decline").status_code == 200
    for decision in ("approve", "decline"):
        response = decide(client, trip, second["request"]["id"], creator, decision)
        assert response.status_code == 409 and error_code(response) == "request_closed"
    assert get_trip(client, trip, trip["yusuf"]["token"]).status_code == 200


def test_unknown_requests_and_other_trips_requests_are_not_found(client, trip):
    other = client.post("/api/trips", json={"trip_name": "Nile felucca trip", "display_name": "Amara"}).json()
    code = other["trip"]["join_code"]
    client.post("/api/trips/join", json={"join_code": code, "display_name": "Omar"})
    elsewhere = client.post("/api/trips/rejoin", json={"join_code": code, "display_name": "Omar"}).json()

    for request_id in ("made-up-id", elsewhere["request"]["id"]):
        response = decide(client, trip, request_id, trip["creator"]["token"], "approve")
        assert response.status_code == 404 and error_code(response) == "request_not_found"
    assert listed(client, trip, trip["creator"]["token"]) == []  # the other trip's request isn't listed here


def test_a_request_decided_between_the_check_and_the_save_is_still_closed(client, trip, monkeypatch):
    asked = ask_to_rejoin(client, trip, "Yusuf")
    may_decide = rejoin._may_decide

    def someone_else_declines_first(*args):
        with connect() as conn:
            conn.execute(
                "UPDATE rejoin_requests SET status = 'declined', closed_at = ? WHERE id = ?",
                (utc_now_iso(), asked["request"]["id"]),
            )
        return may_decide(*args)

    monkeypatch.setattr(rejoin, "_may_decide", someone_else_declines_first)

    response = decide(client, trip, asked["request"]["id"], trip["creator"]["token"], "approve")

    assert response.status_code == 409 and error_code(response) == "request_closed"
    assert get_trip(client, trip, trip["yusuf"]["token"]).status_code == 200
    assert error_code(get_trip(client, trip, asked["token"])) == "token_invalid"


def test_requests_are_listed_and_decided_in_an_ended_trip(client, trip):
    with connect() as conn:
        conn.execute("UPDATE trips SET status = 'ended', ended_at = ? WHERE id = ?", (utc_now_iso(), trip["trip"]["id"]))
    asked = ask_to_rejoin(client, trip, "Chidi")

    assert [r["id"] for r in listed(client, trip, trip["creator"]["token"])] == [asked["request"]["id"]]
    assert decide(client, trip, asked["request"]["id"], trip["creator"]["token"], "approve").status_code == 200
    assert get_trip(client, trip, asked["token"]).status_code == 200


def test_listing_and_deciding_need_a_member_of_this_trip(client, trip):
    asked = ask_to_rejoin(client, trip, "Yusuf")
    outsider = client.post("/api/trips", json={"trip_name": "Faroe Islands hike", "display_name": "Sigrid"}).json()

    assert error_code(client.get(requests_url(trip))) == "token_missing"
    assert error_code(client.get(requests_url(trip), headers=bearer(outsider["token"]))) == "not_a_member"
    response = decide(client, trip, asked["request"]["id"], outsider["token"], "approve")
    assert response.status_code == 403 and error_code(response) == "not_a_member"
    assert error_code(decide(client, trip, asked["request"]["id"], asked["token"], "approve")) == "token_invalid"
