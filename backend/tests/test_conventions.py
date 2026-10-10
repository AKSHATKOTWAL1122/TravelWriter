import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from storymaker.api import ApiError, api_router
from storymaker.ids import new_id
from storymaker.main import create_app
from storymaker.times import normalize_iso, parse_iso, to_iso, utc_now_iso

TIME_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class NameBody(BaseModel):
    name: str


@pytest.fixture
def test_routes_client():
    """Adds test-only routes to the shared /api router, builds a fresh app, then removes them."""
    before = len(api_router.routes)

    @api_router.get("/_test/ping")
    def ping():
        return {"pong": True}

    @api_router.get("/_test/missing-trip")
    def missing_trip():
        raise ApiError(404, "trip_not_found", "That trip doesn't exist.")

    @api_router.post("/_test/named")
    def named(body: NameBody):
        return {"name": body.name}

    @api_router.get("/_test/crash")
    def crash():
        raise RuntimeError("secret internal detail")

    try:
        # The server-error handler still responds; don't re-raise inside the test client.
        with TestClient(create_app(), raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        del api_router.routes[before:]


def test_shared_router_routes_live_under_api(test_routes_client):
    response = test_routes_client.get("/api/_test/ping")

    assert response.status_code == 200
    assert response.json() == {"pong": True}
    assert test_routes_client.get("/_test/ping").status_code == 404  # not outside /api


def test_health_stays_at_the_root(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_api_error_has_the_shared_shape(test_routes_client):
    response = test_routes_client.get("/api/_test/missing-trip")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "trip_not_found", "message": "That trip doesn't exist."}}


def test_bad_request_names_the_field(test_routes_client):
    response = test_routes_client.post("/api/_test/named", json={})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "name" in error["message"]


def test_unknown_path_is_not_found_in_the_same_shape(client):
    response = client.get("/api/no-such-thing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert set(response.json()["error"]) == {"code", "message"}


def test_unexpected_error_hides_internal_details(test_routes_client):
    response = test_routes_client.get("/api/_test/crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


def test_test_only_routes_are_removed_afterwards():
    assert not any("/_test/" in route.path for route in api_router.routes)


def test_time_format_is_utc_with_milliseconds_and_z():
    assert TIME_FORMAT.match(utc_now_iso())
    assert to_iso(datetime(2026, 10, 10, 14, 30, 0, 123456, tzinfo=timezone.utc)) == "2026-10-10T14:30:00.123Z"


def test_times_with_an_offset_are_converted_to_utc():
    assert normalize_iso("2026-10-10T20:00:00+05:30") == "2026-10-10T14:30:00.000Z"
    assert normalize_iso("2026-10-10T14:30:00Z") == "2026-10-10T14:30:00.000Z"


def test_times_without_a_zone_are_rejected():
    with pytest.raises(ValueError, match="no time zone"):
        parse_iso("2026-10-10T14:30:00")


def test_text_order_matches_time_order():
    moments = [
        datetime(2026, 10, 10, 9, 5, 0, 7000, tzinfo=timezone.utc),
        datetime(2026, 10, 10, 14, 30, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 9, 23, 59, 59, 999000, tzinfo=timezone.utc),
        datetime(2026, 10, 10, 9, 5, 0, 6000, tzinfo=timezone.utc),
    ]
    assert sorted(to_iso(m) for m in moments) == [to_iso(m) for m in sorted(moments)]


def test_new_ids_are_random_url_safe_strings():
    ids = [new_id() for _ in range(10_000)]

    assert len(set(ids)) == 10_000
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{22}", i) for i in ids)
