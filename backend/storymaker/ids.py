import secrets


def new_id() -> str:
    """A random, URL-safe ID (22 characters, 128 bits). Never a counting number (spec 01.4)."""
    return secrets.token_urlsafe(16)
