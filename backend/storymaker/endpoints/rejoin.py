"""Rejoin requests: a member on a new phone asks to get back in as themselves (spec 02.7),
whoever may decide approves or declines (spec 02.8; the creator's own request goes to their
backup, spec 02.10), and the new phone checks how its request ended (spec 02.9).

The answer carries the new phone's token, but only its hash is stored, on the request
(ISSUE-055). The token opens nothing until approval moves that hash onto the member;
the member's current login keeps working until then.
"""

import sqlite3
from typing import Annotated

from fastapi import Depends, Header
from pydantic import BaseModel

from ..api import ApiError, api_router
from ..auth import STILL_SIGNED_IN, CurrentMember, bearer_token, token_invalid, trip_member
from ..db import get_db
from ..ids import new_id
from ..names import MemberName, name_key
from ..times import utc_now_iso
from ..tokens import hash_token, new_token
from .backup import STILL_THE_BACKUP, backup_member_id
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


class PendingRequest(RejoinRequest):
    """02.7's request object plus the member it asks for."""

    member: Member


class RejoinRequestsResponse(BaseModel):
    requests: list[PendingRequest]


class RejoinRequestResponse(BaseModel):
    request: RejoinRequest


def _may_decide(caller: CurrentMember, member_id: str, member_role: str, backup_id: str | None) -> bool:
    """Who decides a rejoin request: the creator, for every other member's request, and the
    creator's backup alone for the creator's own (02.10). With no backup, nobody can decide
    the creator's request yet (02.11). Nobody decides a request for themselves."""
    if member_id == caller.id:
        return False
    if member_role == "creator":
        return caller.id == backup_id
    return caller.role == "creator"


@api_router.get("/trips/{trip_id}/rejoin-requests")
def list_rejoin_requests(
    caller: Annotated[CurrentMember, Depends(trip_member)], conn: Annotated[sqlite3.Connection, Depends(get_db)]
) -> RejoinRequestsResponse:
    """The pending requests the caller may decide, oldest first."""
    backup_id = backup_member_id(conn, caller.trip_id)
    rows = conn.execute(
        "SELECT r.id, r.status, r.created_at, m.id AS member_id, m.display_name, m.role, m.joined_at "
        "FROM rejoin_requests r JOIN members m ON m.id = r.member_id "
        "WHERE m.trip_id = ? AND r.status = 'pending' ORDER BY r.created_at, r.id",
        (caller.trip_id,),
    )
    return RejoinRequestsResponse(
        requests=[
            PendingRequest(
                id=row["id"],
                status=row["status"],
                created_at=row["created_at"],
                member=Member(
                    id=row["member_id"], display_name=row["display_name"], role=row["role"], joined_at=row["joined_at"]
                ),
            )
            for row in rows
            if _may_decide(caller, row["member_id"], row["role"], backup_id)
        ]
    )


def _not_allowed(member_role: str, backup_id: str | None) -> ApiError:
    """The answer for a request the caller may not decide, saying who can (02.10)."""
    if member_role != "creator":
        return ApiError(403, "not_allowed", "Only the trip's creator can approve or decline this request.")
    if backup_id is None:
        return ApiError(
            403, "not_allowed", "The creator has no backup, so nobody can approve or decline their request yet."
        )
    return ApiError(403, "not_allowed", "Only the creator's backup can approve or decline this request.")


def _decide(conn: sqlite3.Connection, caller: CurrentMember, request_id: str, status: str) -> RejoinRequestResponse:
    row = conn.execute(
        "SELECT r.member_id, r.created_at, m.role FROM rejoin_requests r JOIN members m ON m.id = r.member_id "
        "WHERE r.id = ? AND m.trip_id = ?",
        (request_id, caller.trip_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "request_not_found", "There's no such rejoin request in this trip.")
    backup_id = backup_member_id(conn, caller.trip_id)
    if not _may_decide(caller, row["member_id"], row["role"], backup_id):
        raise _not_allowed(row["role"], backup_id)

    # The save carries every condition the check relied on (ISSUE-064): the request is still pending
    # (so if two people decide at once, the first wins), the caller's login still works (02.4), and
    # for the creator's request, the backup is still the one checked (02.10).
    conditions = f"id = ? AND status = 'pending' AND {STILL_SIGNED_IN}"
    args = [request_id, caller.id, caller.token_hash]
    if row["role"] == "creator":
        conditions += f" AND {STILL_THE_BACKUP}"
        args += [caller.trip_id, backup_id]

    with conn:  # one transaction: the request is closed and, on approval, the login moves, or neither happens
        closed = conn.execute(
            f"UPDATE rejoin_requests SET status = ?, closed_at = ? WHERE {conditions}", (status, utc_now_iso(), *args)
        ).rowcount
        if not closed:
            # Nothing was saved. Say which condition failed, in the order a fresh call would find it.
            if not conn.execute(f"SELECT {STILL_SIGNED_IN}", (caller.id, caller.token_hash)).fetchone()[0]:
                raise token_invalid()
            if row["role"] == "creator" and (now_backup := backup_member_id(conn, caller.trip_id)) != backup_id:
                raise _not_allowed(row["role"], now_backup)
            raise ApiError(409, "request_closed", "This request was already approved, declined or replaced.")
        if status == "approved":
            # The new phone's token starts working the moment the old one stops (ISSUE-055).
            conn.execute(
                "UPDATE members SET token_hash = (SELECT token_hash FROM rejoin_requests WHERE id = ?) WHERE id = ?",
                (request_id, row["member_id"]),
            )
    return RejoinRequestResponse(request=RejoinRequest(id=request_id, status=status, created_at=row["created_at"]))


@api_router.post("/trips/{trip_id}/rejoin-requests/{request_id}/approve")
def approve_rejoin_request(
    request_id: str,
    caller: Annotated[CurrentMember, Depends(trip_member)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> RejoinRequestResponse:
    """Approve: the request's token becomes the member's, and their old phone's login stops working."""
    return _decide(conn, caller, request_id, "approved")


@api_router.post("/trips/{trip_id}/rejoin-requests/{request_id}/decline")
def decline_rejoin_request(
    request_id: str,
    caller: Annotated[CurrentMember, Depends(trip_member)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> RejoinRequestResponse:
    """Decline: the request's token never works; the member's current login is untouched."""
    return _decide(conn, caller, request_id, "declined")


@api_router.get("/trips/{trip_id}/rejoin-requests/{request_id}")
def check_rejoin_request(
    trip_id: str,
    request_id: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> RejoinRequestResponse:
    """The new phone checks its request with the token that came with it (02.7), whatever the status.
    The token is matched against the request, not the members, so it works while still pending.
    Any other token gets the same answer as a made-up ID, so nobody can probe for requests or trips."""
    row = conn.execute(
        "SELECT r.id, r.status, r.created_at FROM rejoin_requests r JOIN members m ON m.id = r.member_id "
        "WHERE r.id = ? AND m.trip_id = ? AND r.token_hash = ?",
        (request_id, trip_id, hash_token(bearer_token(authorization))),
    ).fetchone()
    if row is None:
        raise ApiError(404, "request_not_found", "There's no such rejoin request in this trip.")
    return RejoinRequestResponse(request=RejoinRequest(**dict(row)))
