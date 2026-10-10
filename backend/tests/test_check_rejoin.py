import pytest

from storymaker.db import connect
from storymaker.times import utc_now_iso


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def trip(client):
    """A trip with its creator and two friends, each with their phone's token."""
    created = client.post("/api/trips", json={"trip_name": "Atacama stargazing", "display_name": "Hana"}).json()
    code = created["trip"]["join_code"]
    tomas = client.post("/api/trips/join", json={"join_code": code, "display_name": "Tomás"}).json()
    wiremu = client.post("/api/trips/join", json={"join_code": code, "display_name": "Wiremu"}).json()
    return {"trip": created["trip"], "creator": created, "tomas": tomas, "wiremu": wiremu}


def ask_to_rejoin(client, trip, display_name):
    response = client.post("/api/trips/rejoin", json={"join_code": trip["trip"]["join_code"], "display_name": display_name})
    assert response.status_code == 201
    return response.json()


def request_url(trip_id, request_id):
    return f"/api/trips/{trip_id}/rejoin-requests/{request_id}"


def check(client, asked, token=None, trip_id=None, request_id=None):
    """Check a request: by default the one in `asked`, with its own token."""
    url = request_url(trip_id or asked["trip"]["id"], request_id or asked["request"]["id"])
    return client.get(url, headers=bearer(token or asked["token"]))


def decide(client, trip, asked, decision):
    url = f"{request_url(trip['trip']['id'], asked['request']['id'])}/{decision}"
    assert client.post(url, headers=bearer(trip["creator"]["token"])).status_code == 200


def get_trip(client, trip, token):
    return client.get(f"/api/trips/{trip['trip']['id']}", headers=bearer(token))


def error_code(response):
    return response.json()["error"]["code"]


def database_rows():
    with connect() as conn:
        return [
            [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
            for table in ("trips", "members", "rejoin_requests")
        ]


def test_a_pending_request_checks_as_pending_and_its_token_opens_nothing_else(client, trip):
    asked = ask_to_rejoin(client, trip, "tomás ")

    response = check(client, asked)

    assert response.status_code == 200
    assert response.json() == {"request": asked["request"]}
    assert response.json()["request"]["status"] == "pending"
    assert error_code(get_trip(client, trip, asked["token"])) == "token_invalid"


def test_once_approved_the_same_token_loads_the_trip(client, trip):
    asked = ask_to_rejoin(client, trip, "Tomás")
    decide(client, trip, asked, "approve")

    response = check(client, asked)

    assert response.status_code == 200
    assert response.json() == {"request": {**asked["request"], "status": "approved"}}
    loaded = get_trip(client, trip, asked["token"])
    assert loaded.status_code == 200
    assert trip["tomas"]["member"] in loaded.json()["members"]


def test_declined_and_replaced_requests_check_as_such_each_with_its_own_token(client, trip):
    declined = ask_to_rejoin(client, trip, "Tomás")
    decide(client, trip, declined, "decline")
    assert check(client, declined).json()["request"]["status"] == "declined"

    first = ask_to_rejoin(client, trip, "Tomás")
    second = ask_to_rejoin(client, trip, "Tomás")  # replaces the first

    assert check(client, first).json() == {"request": {**first["request"], "status": "replaced"}}
    assert check(client, second).json() == {"request": second["request"]}
    assert error_code(check(client, first, token=second["token"])) == "request_not_found"
    assert error_code(check(client, second, token=first["token"])) == "request_not_found"


def test_only_the_requests_own_token_opens_it(client, trip):
    asked = ask_to_rejoin(client, trip, "Tomás")
    other_request = ask_to_rejoin(client, trip, "Wiremu")
    elsewhere = client.post("/api/trips", json={"trip_name": "Dolomites via ferrata", "display_name": "Giulia"}).json()

    for headers in ({}, {"Authorization": f"Basic {asked['token']}"}, {"Authorization": "Bearer "}):
        response = client.get(request_url(trip["trip"]["id"], asked["request"]["id"]), headers=headers)
        assert response.status_code == 401 and error_code(response) == "token_missing"
    for token in (trip["tomas"]["token"], trip["creator"]["token"], other_request["token"], "made-up-token"):
        response = check(client, asked, token=token)
        assert response.status_code == 404 and error_code(response) == "request_not_found"
    for where in ({"request_id": "made-up-id"}, {"trip_id": elsewhere["trip"]["id"]}, {"trip_id": "made-up-trip"}):
        response = check(client, asked, **where)
        assert response.status_code == 404 and error_code(response) == "request_not_found"


def test_checking_works_in_an_ended_trip_and_changes_nothing(client, trip):
    with connect() as conn:
        conn.execute("UPDATE trips SET status = 'ended', ended_at = ? WHERE id = ?", (utc_now_iso(), trip["trip"]["id"]))
    asked = ask_to_rejoin(client, trip, "Tomás")
    before = database_rows()

    for _ in range(2):
        assert check(client, asked).json() == {"request": asked["request"]}
    check(client, asked, token="made-up-token")

    assert database_rows() == before
