"""Rejoin request (spec 02.7): a member on a new phone asks to get back in as themselves.

The answer carries the new phone's token, but only its hash is stored, on the request
(ISSUE-055). The token opens nothing until approval (spec 02.8) moves that hash onto
the member; the member's current login keeps working until then.
"""

import sqlite3
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel

from ..api import ApiError, api_router
from ..db import get_db
from ..ids import new_id
from ..names import MemberName, name_key
from ..times import utc_now_iso
from ..tokens import new_token
from .join import trip_by_code
from .trips import Member, Trip


class RejoinTripRequest(BaseModel):
    join_code: str
    display_name: MemberName


class RejoinRequest(BaseModel):
    id: str
    status: str
    created_at: str


class RejoinTripResponse(BaseModel):
    request: RejoinRequest
    trip: Trip
    member: Member
    token: str


@api_router.post("/trips/rejoin", status_code=201)
def ask_to_rejoin(body: RejoinTripRequest, conn: Annotated[sqlite3.Connection, Depends(get_db)]) -> RejoinTripResponse:
    """Ask to get back into a trip as an existing member. No token needed; works in ended trips too."""
    trip = trip_by_code(conn, body.join_code)
    row = conn.execute(
        "SELECT id, display_name, role, joined_at FROM members WHERE trip_id = ? AND name_key = ?",
        (trip.id, name_key(body.display_name)),
    ).fetchone()
    if row is None:
        raise ApiError(
            404, "member_not_found", "Nobody in this trip has that name. Check the spelling, or join as someone new."
        )
    member = Member(**dict(row))
    request = RejoinRequest(id=new_id(), status="pending", created_at=utc_now_iso())
    token, token_hash = new_token()

    with conn:  # one transaction: an earlier pending request is replaced as this one is saved (ISSUE-054)
        conn.execute(
            "UPDATE rejoin_requests SET status = 'replaced', closed_at = ? WHERE member_id = ? AND status = 'pending'",
            (request.created_at, member.id),
        )
        conn.execute(
            "INSERT INTO rejoin_requests (id, member_id, token_hash, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (request.id, member.id, token_hash, request.status, request.created_at),
        )
    return RejoinTripResponse(request=request, trip=trip, member=member, token=token)
