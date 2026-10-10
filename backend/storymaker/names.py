import unicodedata
from typing import Annotated

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError


def name_key(display_name: str) -> str:
    """Comparison form of a member's name: "Zoë", " ZOË " and "zoë" give the same key.

    Unicode-normalized and case-folded so it works in any language (SQLite's
    NOCASE only folds A–Z), with surrounding and repeated spaces removed.
    """
    collapsed = " ".join(display_name.split())
    return unicodedata.normalize("NFKC", collapsed).casefold()


# Name rules (spec 02.3, ISSUE-052). Names are stored exactly as typed; these
# only decide which names are allowed. Words are separated by spaces, so the
# character cap is what limits languages written without them.
MEMBER_NAME_MAX_WORDS = 10
MEMBER_NAME_MAX_CHARS = 60
TRIP_NAME_MAX_WORDS = 50
TRIP_NAME_MAX_CHARS = 300

# Hyphen, apostrophe and period (also typed curly or full-width), and the dots
# Chinese and Japanese put between parts of a name.
NAME_PUNCTUATION = frozenset("-'.’－＇．·・")
# Zero-width non-joiner and joiner: invisible, but Persian and Indian scripts need them.
NAME_JOINERS = frozenset("‌‍")


def _name_rule(*, digits: bool, max_words: int, max_chars: int) -> AfterValidator:
    allowed = f"letters, {'digits, ' if digits else ''}spaces, hyphens, apostrophes and periods"

    def check(name: str) -> str:
        for ch in name:
            category = unicodedata.category(ch)
            # L = letters and M = their accent/vowel marks, in any language; Zs = spaces.
            if not (
                category[0] in "LM"
                or category == "Zs"
                or (digits and category == "Nd")
                or ch in NAME_PUNCTUATION
                or ch in NAME_JOINERS
            ):
                raise PydanticCustomError("name_characters", f"A name can only use {allowed}")
        if not any(unicodedata.category(ch)[0] == "L" for ch in name):
            raise PydanticCustomError("name_no_letter", "A name needs at least one letter")
        if len(name.split()) > max_words:
            raise PydanticCustomError("name_too_many_words", f"A name can be at most {max_words} words")
        if len(name) > max_chars:
            raise PydanticCustomError("name_too_long", f"A name can be at most {max_chars} characters")
        return name

    return AfterValidator(check)


MemberName = Annotated[str, _name_rule(digits=False, max_words=MEMBER_NAME_MAX_WORDS, max_chars=MEMBER_NAME_MAX_CHARS)]
TripName = Annotated[str, _name_rule(digits=True, max_words=TRIP_NAME_MAX_WORDS, max_chars=TRIP_NAME_MAX_CHARS)]
