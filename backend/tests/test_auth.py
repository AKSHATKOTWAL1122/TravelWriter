from dataclasses import asdict
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from storymaker.api import api_router
from storymaker.auth import CurrentMember, current_member, trip_member
from storymaker.db import connect
from storymaker.main import create_app
from storymaker.times import utc_now_iso
from storymaker.tokens import new_token


@pytest.fixture
def auth_client():
    """Adds test-only routes that use the auth dependencies, builds a fresh app, then removes them."""
    before = len(api_router.routes)

    @api_router.get("/_test/me")
    def me(member: Annotated[CurrentMember, Depends(current_member)]):
        return asdict(member)

    @api_router.get("/trips/{trip_id}/_test/me")
    def trip_me(member: Annotated[CurrentMember, Depends(trip_member)]):
        return asdict(member)

    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        del api_router.routes[before:]


def create_trip(client, trip_name, display_name):
    body = client.post("/api/trips", json={"trip_name": trip_name, "display_name": display_name}).json()
    return body["trip"]["id"], body["member"]["id"], body["token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}  # 01.4's shape
    assert body["error"]["code"] == code


def test_the_token_identifies_the_member(auth_client):
    trip_id, member_id, token = create_trip(auth_client, "Andes by bus", "Valentina")

    for header in (f"Bearer {token}", f"bearer {token}"):
        response = auth_client.get("/api/_test/me", headers={"Authorization": header})

        assert response.status_code == 200
        assert response.json() == {"id": member_id, "trip_id": trip_id, "display_name": "Valentina", "role": "creator"}


@pytest.mark.parametrize("header", [None, "Basic dXNlcjpwYXNz", "Bearer", "Bearer   "])
def test_a_missing_or_malformed_header_is_token_missing(auth_client, header):
    headers = {"Authorization": header} if header is not None else {}

    assert_error(auth_client.get("/api/_test/me", headers=headers), 401, "token_missing")


def test_a_made_up_token_is_token_invalid(auth_client):
    create_trip(auth_client, "Andes by bus", "Valentina")

    assert_error(auth_client.get("/api/_test/me", headers=bearer("made-up-token")), 401, "token_invalid")


def test_a_replaced_token_stops_working(auth_client):
    _, member_id, old_token = create_trip(auth_client, "Andes by bus", "Valentina")
    new, new_hash = new_token()
    with connect() as conn:  # what an approved rejoin (02.8) will do
        conn.execute("UPDATE members SET token_hash = ? WHERE id = ?", (new_hash, member_id))

    assert_error(auth_client.get("/api/_test/me", headers=bearer(old_token)), 401, "token_invalid")
    assert auth_client.get("/api/_test/me", headers=bearer(new)).json()["id"] == member_id


def test_trip_routes_turn_away_members_of_other_trips(auth_client):
    trip_a, member_a, token_a = create_trip(auth_client, "Andes by bus", "Valentina")
    trip_b, _, _ = create_trip(auth_client, "Baltic ferries", "Kaarel")

    assert auth_client.get(f"/api/trips/{trip_a}/_test/me", headers=bearer(token_a)).json()["id"] == member_a
    assert_error(auth_client.get(f"/api/trips/{trip_b}/_test/me", headers=bearer(token_a)), 403, "not_a_member")
    assert_error(auth_client.get("/api/trips/no-such-trip/_test/me", headers=bearer(token_a)), 403, "not_a_member")


def test_tokens_keep_working_after_the_trip_ends(auth_client):
    trip_id, member_id, token = create_trip(auth_client, "Andes by bus", "Valentina")
    with connect() as conn:
        conn.execute("UPDATE trips SET status = 'ended', ended_at = ? WHERE id = ?", (utc_now_iso(), trip_id))

    assert auth_client.get("/api/_test/me", headers=bearer(token)).json()["id"] == member_id
    assert auth_client.get(f"/api/trips/{trip_id}/_test/me", headers=bearer(token)).status_code == 200
