import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.domain.card_text import clean_text, match_form

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
SPACES = re.compile(r"\s+")
TWIN_SOURCE = "catalog_twin"


def twin_title(title: str | None) -> str:
    return SPACES.sub(" ", match_form(clean_text(title))).strip()


def title_numbers(title: str) -> frozenset[str]:
    numbers = set()
    for raw in NUMBER.findall(title):
        value = raw.replace(",", ".")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        numbers.add(value.lstrip("0") or "0")
    return frozenset(numbers)


@dataclass(frozen=True, slots=True)
class TwinValue:
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class TwinEntry:
    sku_id: int
    title: str
    numbers: frozenset[str]
    brand: str
    model: str
    values: Mapping[str, TwinValue]


@dataclass(frozen=True, slots=True)
class TwinQuery:
    title: str
    numbers: frozenset[str]
    brand_key: str | None


@dataclass(frozen=True, slots=True)
class Transfer:
    attribute: str
    key: str
    value: str
    similarity: float
    twin_sku: int
    exact: bool
    support: int
    twin_model: str


def brand_matches(entry: TwinEntry, query: TwinQuery) -> bool:
    if not entry.brand:
        return False
    if query.brand_key is not None:
        return query.brand_key == entry.brand
    return f" {entry.brand} " in f" {query.title} "


def is_twin(entry: TwinEntry, query: TwinQuery, similarity: float, floor: float) -> bool:
    return (similarity >= floor and entry.numbers == query.numbers
            and brand_matches(entry, query))


def vote(
    query: TwinQuery, neighbors: Sequence[tuple[TwinEntry, float]], attributes: Iterable[str],
    floor: float,
) -> dict[str, Transfer]:
    twins = [(e, s) for e, s in neighbors if is_twin(e, query, s, floor)]
    if not twins:
        return {}
    result: dict[str, Transfer] = {}
    for attribute in attributes:
        weight: dict[str, float] = defaultdict(float)
        best: dict[str, tuple[TwinEntry, float]] = {}
        support: dict[str, int] = defaultdict(int)
        for entry, similarity in twins:
            value = entry.values.get(attribute)
            if value is None:
                continue
            weight[value.key] += similarity
            support[value.key] += 1
            if value.key not in best or similarity > best[value.key][1]:
                best[value.key] = (entry, similarity)
        if not weight:
            continue
        key = max(weight, key=lambda k: (weight[k], best[k][1], k))
        entry, similarity = best[key]
        result[attribute] = Transfer(attribute, key, entry.values[attribute].value, similarity,
                                     entry.sku_id, entry.title == query.title, support[key],
                                     entry.model)
    return result


def others(
    neighbors: Sequence[tuple[TwinEntry, float]], sku_id: int
) -> list[tuple[TwinEntry, float]]:
    return [(e, s) for e, s in neighbors if e.sku_id != sku_id]


def accepted(transfers: Mapping[str, Transfer], threshold: float) -> dict[str, Transfer]:
    return {name: t for name, t in transfers.items() if t.similarity >= threshold}
