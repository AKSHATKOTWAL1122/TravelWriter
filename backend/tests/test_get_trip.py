import pytest

from storymaker.db import connect
from storymaker.times import utc_now_iso


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_trip(client, trip_name, display_name):
    return client.post("/api/trips", json={"trip_name": trip_name, "display_name": display_name}).json()


def join_trip(client, join_code, display_name):
    return client.post("/api/trips/join", json={"join_code": join_code, "display_name": display_name}).json()


def get_trip(client, trip_id, token):
    return client.get(f"/api/trips/{trip_id}", headers=bearer(token))


@pytest.fixture
def trip(client):
    """A creator and two friends, in that join order (which isn't alphabetical)."""
    created = create_trip(client, "Atlas mountains trek", " Zainab")  # names come back exactly as typed
    code = created["trip"]["join_code"]
    joined = [join_trip(client, code, name) for name in ("Yusuf", "Søren")]
    return {"trip": created["trip"], "people": [created, *joined]}


def assert_error(response, status, code):
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_every_member_gets_the_trip_and_its_members_in_join_order(client, trip):
    people = trip["people"]

    for person in people:
        response = get_trip(client, trip["trip"]["id"], person["token"])

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"trip", "members"}
        assert body["trip"] == trip["trip"]  # 02.3's object, join code included
        assert body["members"] == [p["member"] for p in people]
    assert [m["display_name"] for m in body["members"]] == [" Zainab", "Yusuf", "Søren"]
    assert [m["role"] for m in body["members"]] == ["creator", "member", "member"]


def test_members_are_listed_by_join_time_creator_first(client, trip):
    creator, first, second = (p["member"]["id"] for p in trip["people"])
    # The second friend's time is earliest and the creator's latest, as after the server clock is set back.
    times = {creator: "2026-01-01T09:00:00.000Z", first: "2026-01-01T08:30:00.000Z", second: "2026-01-01T08:00:00.000Z"}
    with connect() as conn:
        for member_id, joined_at in times.items():
            conn.execute("UPDATE members SET joined_at = ? WHERE id = ?", (joined_at, member_id))

    members = get_trip(client, trip["trip"]["id"], trip["people"][0]["token"]).json()["members"]

    assert [m["id"] for m in members] == [creator, second, first]


def test_no_tokens_or_token_hashes_in_the_response(client, trip):
    response = get_trip(client, trip["trip"]["id"], trip["people"][1]["token"])
    with connect() as conn:
        hashes = [row[0] for row in conn.execute("SELECT token_hash FROM members")]

    assert "token" not in response.text
    for secret in [p["token"] for p in trip["people"]] + hashes:
        assert secret not in response.text


def test_outsiders_are_turned_away(client, trip):
    outsider = create_trip(client, "Mekong by slow boat", "Linh")

    assert_error(get_trip(client, trip["trip"]["id"], outsider["token"]), 403, "not_a_member")
    assert_error(get_trip(client, "no-such-trip", trip["people"][0]["token"]), 403, "not_a_member")
    assert_error(client.get(f"/api/trips/{trip['trip']['id']}"), 401, "token_missing")
    assert_error(get_trip(client, trip["trip"]["id"], "made-up-token"), 401, "token_invalid")


def test_an_ended_trip_loads_the_same_way(client, trip):
    with connect() as conn:
        conn.execute("UPDATE trips SET status = 'ended', ended_at = ? WHERE id = ?", (utc_now_iso(), trip["trip"]["id"]))

    response = get_trip(client, trip["trip"]["id"], trip["people"][2]["token"])

    assert response.status_code == 200
    assert response.json()["trip"] == {**trip["trip"], "status": "ended"}
    assert len(response.json()["members"]) == 3
