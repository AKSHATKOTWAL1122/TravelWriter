import unicodedata


def name_key(display_name: str) -> str:
    """Comparison form of a member's name: "Zoë", " ZOË " and "zoë" give the same key.

    Unicode-normalized and case-folded so it works in any language (SQLite's
    NOCASE only folds A–Z), with surrounding and repeated spaces removed.
    """
    collapsed = " ".join(display_name.split())
    return unicodedata.normalize("NFKC", collapsed).casefold()
