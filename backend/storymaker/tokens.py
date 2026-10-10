"""Member tokens (spec 02.3): the key a phone shows with every request.

Only the hash is stored (spec 02.1), so a copied database can't be used to log in.
"""

import hashlib
import secrets


def new_token() -> tuple[str, str]:
    """A new random, URL-safe token (256 bits) and its hash. The token is shown once."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    # Tokens are long and random, so a plain SHA-256 is enough; no slow password hash needed.
    return hashlib.sha256(token.encode()).hexdigest()
