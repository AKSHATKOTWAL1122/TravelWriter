"""Trip endpoints (specs 02.3, 02.6)."""

import sqlite3
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel

from ..api import api_router
from ..auth import CurrentMember, trip_member
from ..db import get_db
from ..ids import new_id
from ..join_codes import new_join_code
from ..names import MemberName, TripName, name_key
from ..times import utc_now_iso
from ..tokens import new_token


class CreateTripRequest(BaseModel):
    trip_name: TripName
    display_name: MemberName


class Trip(BaseModel):
    id: str
    name: str
    join_code: str
    status: str
    created_at: str


class Member(BaseModel):
    id: str
    display_name: str
    role: str
    joined_at: str


class CreateTripResponse(BaseModel):
    trip: Trip
    member: Member
    token: str


@api_router.post("/trips", status_code=201)
def create_trip(
    body: CreateTripRequest, conn: Annotated[sqlite3.Connection, Depends(get_db)]
) -> CreateTripResponse:
    """Start a trip; the caller becomes its creator. No token needed."""
    now = utc_now_iso()
    trip = Trip(id=new_id(), name=body.trip_name, join_code=new_join_code(conn), status="active", created_at=now)
    member = Member(id=new_id(), display_name=body.display_name, role="creator", joined_at=now)
    token, token_hash = new_token()

    with conn:  # one transaction: the trip and its creator are saved together, or neither is
        conn.execute(
            "INSERT INTO trips (id, name, join_code, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (trip.id, trip.name, trip.join_code, trip.status, trip.created_at),
        )
        conn.execute(
            "INSERT INTO members (id, trip_id, display_name, name_key, role, token_hash, joined_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (member.id, trip.id, member.display_name, name_key(member.display_name), member.role, token_hash, now),
        )
    return CreateTripResponse(trip=trip, member=member, token=token)


class GetTripResponse(BaseModel):
    trip: Trip
    members: list[Member]


@api_router.get("/trips/{trip_id}")
def get_trip(
    member: Annotated[CurrentMember, Depends(trip_member)], conn: Annotated[sqlite3.Connection, Depends(get_db)]
) -> GetTripResponse:
    """The trip and who's in it, for its members only. Ended trips load the same way."""
    row = conn.execute(
        "SELECT id, name, join_code, status, created_at FROM trips WHERE id = ?", (member.trip_id,)
    ).fetchone()
    # Join order with the creator always first, even if the times tie or the clock was set back.
    # IDs never change, so ties always come out in the same order.
    rows = conn.execute(
        "SELECT id, display_name, role, joined_at FROM members WHERE trip_id = ? "
        "ORDER BY role != 'creator', joined_at, id",
        (member.trip_id,),
    )
    return GetTripResponse(trip=Trip(**dict(row)), members=[Member(**dict(m)) for m in rows])
