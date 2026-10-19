import re
from collections import defaultdict
from collections.abc import Iterable

from app.domain.card_text import match_form
from benchmarks.files import text_digest


def shingles(text: str) -> frozenset[str]:
    words = re.findall(r"[a-zа-я0-9]+", match_form(text))
    size = min(3, len(words))
    return (
        frozenset(" ".join(words[i : i + size]) for i in range(len(words) - size + 1))
        if size
        else frozenset()
    )


def prefix(parts: frozenset[str]) -> list[str]:
    return sorted(parts)[: len(parts) - (4 * len(parts) + 4) // 5 + 1]


def similar(left: frozenset[str], right: frozenset[str]) -> bool:
    union = len(left | right)
    return bool(union) and 5 * len(left & right) >= 4 * union


class DuplicateIndex:
    def __init__(self, texts: Iterable[str]) -> None:
        values = list(texts)
        self.parts = [shingles(text) for text in values]
        self.exact: dict[str, set[int]] = defaultdict(set)
        for i, text in enumerate(values):
            self.exact[text_digest(match_form(text))].add(i)
        self.index: dict[str, set[int]] = defaultdict(set)
        for i, parts in enumerate(self.parts):
            for token in prefix(parts):
                self.index[token].add(i)

    def matches(self, text: str) -> set[int]:
        parts = shingles(text)
        candidates = {i for token in prefix(parts) for i in self.index.get(token, ())}
        return self.exact.get(text_digest(match_form(text)), set()) | {
            i
            for i in candidates
            if 4 * len(parts) <= 5 * len(self.parts[i])
            and 4 * len(self.parts[i]) <= 5 * len(parts)
            and similar(parts, self.parts[i])
        }
