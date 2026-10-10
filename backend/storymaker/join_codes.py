"""Join codes (spec 02.2): short codes friends type in or get from the share sheet.

6 characters from A–Z and 2–9 without the look-alikes O, I and L, e.g. K7MPQ4.
The database and the API use the plain form; the app may show it grouped (K7M PQ4).
A join code is not an ID: trips get their id from new_id() (spec 01.4).
"""

import secrets
import sqlite3
import unicodedata

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 6
MAX_TRIES = 10


def _random_code() -> str:
    # secrets, not random: codes must not be predictable.
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def new_join_code(conn: sqlite3.Connection) -> str:
    """A code no trip uses yet, ended trips included, so codes are never reused.

    The UNIQUE constraint on trips.join_code (spec 02.1) stays the final guard.
    """
    for _ in range(MAX_TRIES):
        code = _random_code()
        if conn.execute("SELECT 1 FROM trips WHERE join_code = ?", (code,)).fetchone() is None:
            return code
    raise RuntimeError(f"No free join code found after {MAX_TRIES} tries")


def normalize_join_code(typed: str) -> str:
    """What a person typed → the stored form, e.g. " k7m–pq4 " → "K7MPQ4".

    Case, spaces and dashes of any kind are ignored; full-width characters from
    some Asian keyboards count as normal ones. Raises ValueError if it can't be a code.
    """
    text = unicodedata.normalize("NFKC", typed)
    code = "".join(ch for ch in text if not ch.isspace() and unicodedata.category(ch) != "Pd").upper()
    if len(code) != LENGTH or any(ch not in ALPHABET for ch in code):
        raise ValueError(f"{typed!r} is not a join code")
    return code
