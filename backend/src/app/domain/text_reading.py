import math
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.errors import DomainError

VOTE_TEMPERATURE = 0.05
TITLE_MIN_CHARS = 8
TITLE_MAX_CHARS = 160
TITLE_WINDOW_WORDS = 12
WORD = re.compile(r"[a-zа-яё0-9]+(?:[-.][a-zа-яё0-9]+)*", re.IGNORECASE)
SENTENCE_END = re.compile(r"[.!?;:](?:\s|$)")


class EmptyText(DomainError):
    code = "empty_text"
    message = "No product text left after cleaning"


class TextIndexMissing(DomainError):
    code = "text_index_missing"
    message = "Text extraction index is not built"


@dataclass(frozen=True, slots=True)
class TitleSpan:
    start: int
    end: int
    score: float


def rank_categories(hits: Sequence[tuple[int, float]], k: int) -> list[tuple[int, float]]:
    if not hits:
        return []
    top = max(similarity for _, similarity in hits)
    votes: dict[int, float] = defaultdict(float)
    for category, similarity in hits:
        votes[category] += math.exp((similarity - top) / VOTE_TEMPERATURE)
    total = sum(votes.values())
    ranked = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
    return [(category, round(weight / total, 4)) for category, weight in ranked]


def guess_title(text: str, references: Sequence[str]) -> TitleSpan | None:
    wanted = {w.casefold() for r in references for w in WORD.findall(r)}
    best: TitleSpan | None = None
    offset = 0
    for line in text.split("\n"):
        span = _best_window(line, offset, wanted)
        if span is not None and (best is None or span.score > best.score):
            best = span
        offset += len(line) + 1
    return best


def _best_window(line: str, offset: int, wanted: set[str]) -> TitleSpan | None:
    head = SENTENCE_END.search(line)
    sentence = line[: head.start()] if head else line
    words = list(WORD.finditer(sentence))[:TITLE_WINDOW_WORDS]
    if not words:
        return None
    start, end = words[0].start(), words[-1].end()
    if not TITLE_MIN_CHARS <= end - start <= TITLE_MAX_CHARS:
        return None
    hits = sum(1 for w in words if w.group().casefold() in wanted)
    score = hits / len(words) if wanted else 1.0 / (1 + offset)
    return TitleSpan(offset + start, offset + end, round(score, 4))
