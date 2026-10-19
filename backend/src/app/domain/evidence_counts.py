import re

from app.domain.attribute_flow import FieldAnswer
from app.domain.card_text import match_form
from app.domain.evidence_words import field_matches

COUNTER = re.compile(r"^(?:количество|число)\s+(.+)$")
CARDINALS = {
    "один": 1,
    "одна": 1,
    "одно": 1,
    "одним": 1,
    "одной": 1,
    "одного": 1,
    "два": 2,
    "две": 2,
    "двух": 2,
    "двумя": 2,
    "три": 3,
    "трех": 3,
    "тремя": 3,
    "четыре": 4,
    "четырех": 4,
    "четырьмя": 4,
    "пять": 5,
    "пяти": 5,
    "пятью": 5,
    "шесть": 6,
    "шести": 6,
    "шестью": 6,
}


def count_evidence(answer: FieldAnswer, evidence: str, unit: str = "") -> str | None:
    counter = COUNTER.match(match_form(answer.attribute))
    if counter is None or answer.unit not in {"", "шт"}:
        return None
    found = []
    text = match_form(evidence)
    for match in re.finditer(r"\b(?:\d+|" + "|".join(CARDINALS) + r")\b", text):
        tail = re.split(r"[,;.!?]|\b(?:и|или|но)\b", text[match.end() :], maxsplit=1)[0]
        words = re.findall(r"[a-zа-я]+", tail)
        if not words or not field_matches(" ".join(words[:3]), (counter[1],)):
            continue
        number = str(CARDINALS.get(match[0], match[0]))
        limit = re.search(
            r"\b(не более|не менее|до|от|около|более|менее)\s*$", text[: match.start()]
        )
        quantity = f"{number} {unit}".strip()
        found.append(f"{limit[1]} {quantity}" if limit else quantity)
    return found[0] if len(set(found)) == 1 else None
