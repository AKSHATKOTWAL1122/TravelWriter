"""The creator's backup (spec 02.10): the one other member who decides the creator's own
rejoin request (spec 02.8), so someone who only has the join code can't join and approve
their own takeover of the creator (ISSUE-056).
"""

import sqlite3
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel

from ..api import ApiError, api_router
from ..auth import CurrentMember, trip_member
from ..db import get_db


class Backup(BaseModel):
    """The request and the answer: the backup's member ID, or null for none (the field is required)."""

    backup_member_id: str | None


def backup_member_id(conn: sqlite3.Connection, trip_id: str) -> str | None:
    """The trip's backup, or None. Also used by 02.6 (who it is) and 02.8 (who decides)."""
    row = conn.execute("SELECT id FROM members WHERE trip_id = ? AND is_backup = 1", (trip_id,)).fetchone()
    return row["id"] if row else None


@api_router.put("/trips/{trip_id}/backup")
def pick_backup(
    body: Backup,
    caller: Annotated[CurrentMember, Depends(trip_member)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> Backup:
    """The creator picks one other member as backup, replacing any earlier one, or none. Works in ended trips too."""
    if caller.role != "creator":
        raise ApiError(403, "creator_only", "Only the trip's creator can pick the backup.")
    picked = body.backup_member_id
    if picked == caller.id:
        raise ApiError(
            422, "validation_error", "Invalid request: 'backup_member_id': the backup must be someone other than the creator."
        )
    if picked is not None and not conn.execute(
        "SELECT 1 FROM members WHERE id = ? AND trip_id = ?", (picked, caller.trip_id)
    ).fetchone():
        raise ApiError(404, "member_not_found", "Nobody in this trip has that member ID.")

    with conn:  # one transaction: the earlier backup steps down as the new one is picked
        conn.execute("UPDATE members SET is_backup = 0 WHERE trip_id = ? AND is_backup = 1", (caller.trip_id,))
        if picked is not None:
            conn.execute("UPDATE members SET is_backup = 1 WHERE id = ?", (picked,))
    return Backup(backup_member_id=picked)
