import re

from app.domain.values import NUMBER, UNIT_ALIASES

UNIT = (
    "(?:"
    + "|".join(re.escape(unit) for unit in sorted(UNIT_ALIASES, key=len, reverse=True))
    + r")(?!\w|\s*[/·⋅×*^]|[²³])"
)
SIGNED = rf"[+−-]?\s*{NUMBER}"
QUANTITY = re.compile(
    rf"(?<![\w.,])(?:"
    rf"(?:от\s*)?{SIGNED}\s*(?:{UNIT}\s*)?(?:[-–—…]|до)\s*{SIGNED}\s*{UNIT}"
    rf"|(?:не более|не менее|до|от|более|менее|свыше|около)\s*{SIGNED}\s*{UNIT}"
    rf"|{SIGNED}\s*{UNIT})"
)


def quantity_fragments(evidence: str, quote: str | None) -> tuple[str, ...]:
    found = tuple(QUANTITY.finditer(evidence))
    if quote:
        literal = quote.rstrip(" .;!?\n")
        position = evidence.find(literal) if literal else -1
        if position >= 0:
            found = tuple(
                m for m in found if m.start() < position + len(literal) and m.end() > position
            )
    return tuple(m[0] for m in found)
