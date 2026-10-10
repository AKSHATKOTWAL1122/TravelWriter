"""Join-trip endpoint (spec 02.5)."""

import sqlite3
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel

from ..api import ApiError, api_router
from ..db import get_db
from ..ids import new_id
from ..join_codes import normalize_join_code
from ..names import MemberName, name_key
from ..times import utc_now_iso
from ..tokens import new_token
from .trips import Member, Trip


class JoinTripRequest(BaseModel):
    join_code: str
    display_name: MemberName


class JoinTripResponse(BaseModel):
    """Same shape as creating a trip (spec 02.3)."""

    trip: Trip
    member: Member
    token: str


def _name_in_use(conn: sqlite3.Connection, trip_id: str, key: str) -> bool:
    return conn.execute("SELECT 1 FROM members WHERE trip_id = ? AND name_key = ?", (trip_id, key)).fetchone() is not None


def _name_taken() -> ApiError:
    return ApiError(
        409,
        "name_taken",
        "Someone in this trip already uses that name. "
        "If it's you on a new phone, choose \"I'm already in this trip\".",
    )


@api_router.post("/trips/join", status_code=201)
def join_trip(body: JoinTripRequest, conn: Annotated[sqlite3.Connection, Depends(get_db)]) -> JoinTripResponse:
    """Join a trip with its code. No token needed; ended trips can still be joined."""
    try:
        code = normalize_join_code(body.join_code)
    except ValueError:
        code = None
    row = code and conn.execute(
        "SELECT id, name, join_code, status, created_at FROM trips WHERE join_code = ?", (code,)
    ).fetchone()
    if not row:
        raise ApiError(404, "trip_not_found", "No trip has that code. Check it and try again.")
    trip = Trip(**dict(row))

    key = name_key(body.display_name)
    if _name_in_use(conn, trip.id, key):
        raise _name_taken()
    member = Member(id=new_id(), display_name=body.display_name, role="member", joined_at=utc_now_iso())
    token, token_hash = new_token()
    try:
        with conn:
            conn.execute(
                "INSERT INTO members (id, trip_id, display_name, name_key, role, token_hash, joined_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (member.id, trip.id, member.display_name, key, member.role, token_hash, member.joined_at),
            )
    except sqlite3.IntegrityError as error:
        # Someone took the name between the check and the save (02.1's unique name index).
        if "members.trip_id, members.name_key" in str(error):
            raise _name_taken() from error
        raise
    return JoinTripResponse(trip=trip, member=member, token=token)
