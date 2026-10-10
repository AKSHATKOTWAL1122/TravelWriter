"""One time format for the API and the database (spec 01.4).

Always UTC, milliseconds, and a trailing Z, e.g. 2026-10-10T14:30:00.123Z.
The width is fixed, so sorting these strings as text sorts them by time.
"""

from datetime import datetime, timezone


def to_iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("datetime must carry a time zone")
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def utc_now_iso() -> str:
    return to_iso(datetime.now(timezone.utc))


def parse_iso(value: str) -> datetime:
    """Parse an incoming time; it must carry a time zone (Z or an offset like +05:30)."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(f"Time {value!r} has no time zone")
    return moment.astimezone(timezone.utc)


def normalize_iso(value: str) -> str:
    """Incoming time in any zone → the one stored/returned format."""
    return to_iso(parse_iso(value))
