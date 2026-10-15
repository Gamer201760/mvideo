import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

TEXT_DESCRIPTION_CHARS = 120
_TAGS = re.compile(r"<[^>]{0,200}>")
_SPACES = re.compile(r"\s+")


class CategorySource(StrEnum):
    CATALOG = "catalog"
    CLICKS = "clicks"
    CLASSIFIER = "classifier"


@dataclass(frozen=True, slots=True)
class CategoryGuess:
    sku_id: int
    category_id: int
    source: CategorySource
    confidence: float


@dataclass(frozen=True, slots=True)
class ClickMapping:
    category_id: int
    share: float


Ranked = Sequence[tuple[int, float]]


def category_text(title: str | None, description: str | None) -> str:
    head = _TAGS.sub(" ", (description or "")[: TEXT_DESCRIPTION_CHARS * 2])
    text = f"{title or ''} {head[:TEXT_DESCRIPTION_CHARS]}".lower().replace("ё", "е")
    return _SPACES.sub(" ", text).strip()


def majority_mapping(pairs: Iterable[tuple[int, int, int]]) -> dict[int, ClickMapping]:
    counts: dict[int, Counter[int]] = defaultdict(Counter)
    for click_category, catalog_category, clicks in pairs:
        counts[click_category][catalog_category] += clicks
    mapping = {}
    for click_category, votes in counts.items():
        best, top = votes.most_common(1)[0]
        mapping[click_category] = ClickMapping(best, top / sum(votes.values()))
    return mapping


def resolve(
    sku_id: int,
    catalog: int | None,
    clicks: ClickMapping | None,
    ranked: Ranked,
    threshold: float,
) -> CategoryGuess | None:
    if catalog is not None:
        return CategoryGuess(sku_id, catalog, CategorySource.CATALOG, 1.0)
    if clicks is not None:
        return CategoryGuess(sku_id, clicks.category_id, CategorySource.CLICKS, clicks.share)
    if ranked and ranked[0][1] >= threshold:
        category, confidence = ranked[0]
        return CategoryGuess(sku_id, category, CategorySource.CLASSIFIER, confidence)
    return None
