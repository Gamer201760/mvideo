import re
from collections.abc import Iterator

MAX_NGRAM = 3
_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[a-zа-я]+")


def tokens(text: str) -> list[str]:
    lowered = text.lower().replace("ё", "е")
    return [token.replace(",", ".") for token in _TOKEN.findall(lowered)]


def ngrams(text: str, size: int = MAX_NGRAM) -> Iterator[str]:
    parts = tokens(text)
    seen: set[str] = set()
    for n in range(1, size + 1):
        for start in range(len(parts) - n + 1):
            gram = " ".join(parts[start : start + n])
            if gram not in seen:
                seen.add(gram)
                yield gram


def value_key(value: str, unit: str | None) -> str | None:
    parts = tokens(value)
    if not parts:
        return None
    if all(part[0].isdigit() for part in parts):
        if not unit:
            return None
        parts = parts + tokens(unit)
    if len(parts) > MAX_NGRAM:
        return None
    return " ".join(parts)
