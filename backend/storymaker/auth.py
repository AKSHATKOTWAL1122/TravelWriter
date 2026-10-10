"""Member token auth (spec 02.4): which member is calling, from the phone's token.

The phone sends "Authorization: Bearer <token>". Tokens don't expire; one works
until a rejoin replaces its hash (spec 02.8), also after the trip has ended.
"""

import sqlite3
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header

from .api import ApiError
from .db import get_db
from .tokens import hash_token


@dataclass(frozen=True)
class CurrentMember:
    id: str
    trip_id: str
    display_name: str
    role: str


def bearer_token(authorization: str | None) -> str:
    """The token from an "Authorization: Bearer <token>" header. Also used by spec 02.9,
    whose token belongs to a rejoin request rather than a member."""
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "token_missing", "This phone isn't signed in to a trip.")
    return token


def current_member(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentMember:
    """FastAPI dependency: the member whose token came with the request."""
    row = conn.execute(
        "SELECT id, trip_id, display_name, role FROM members WHERE token_hash = ?",
        (hash_token(bearer_token(authorization)),),
    ).fetchone()
    if row is None:
        raise ApiError(401, "token_invalid", "This phone's login for the trip no longer works.")
    return CurrentMember(**dict(row))


def trip_member(trip_id: str, member: Annotated[CurrentMember, Depends(current_member)]) -> CurrentMember:
    """current_member for paths with a {trip_id}. Members of other trips are turned away,
    and so is a trip ID that doesn't exist, so outsiders can't probe for trips."""
    if member.trip_id != trip_id:
        raise ApiError(403, "not_a_member", "You're not a member of this trip.")
    return member
