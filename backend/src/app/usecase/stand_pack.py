from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.lexicon import Lexicon
from app.domain.profile import TZ_REQUIRED, AttributeProfile, profile_attribute
from app.domain.values import canonical_key
from app.usecase.baseline_ports import BaselineSource, CardRecord, RequiredRecord
from app.usecase.extraction import UNKNOWN_CATEGORY_ATTRIBUTES, RequiredAttributes, extract_card
from app.usecase.interface import Logger
from app.usecase.lexicon_builder import LexiconConfig, TrainValue, attribute_entries
from app.usecase.stand_ports import StandCategory, StandExample, StandPack, StandPackSink
from app.usecase.stand_twin_pack import TwinRows, build_stand_twins

FOCUS = (761, 987)


class CategoryNames(Protocol):
    def names(self) -> Mapping[int, tuple[str, str]]: ...


@dataclass(frozen=True, slots=True)
class StandPackConfig:
    categories: int = 30
    focus_examples: int = 6
    other_examples: int = 1
    max_examples: int = 40
    threshold: float = 0.35
    min_description: int = 200
    twins_per_category: int = 1500


@dataclass(slots=True)
class Counts:
    values: dict[str, Counter[tuple[str, str | None]]]
    per_category: dict[tuple[int, str], Counter[tuple[str, str | None]]]


class BuildStandPack:
    def __init__(self, source: BaselineSource, names: CategoryNames, sink: StandPackSink,
                 logger: Logger, twin_rows: TwinRows | None = None) -> None:
        self._source = source
        self._names = names
        self._sink = sink
        self._logger = logger
        self._twin_rows = twin_rows

    def run(self, config: StandPackConfig, now: datetime) -> int:
        records = self._source.required()
        chosen = choose_categories(records, self._source.category_stats(), config.categories)
        required = [r for r in records if r.category_id in chosen]
        attributes = {r.attribute for r in required} | set(UNKNOWN_CATEGORY_ATTRIBUTES)
        attributes |= {a for c in FOCUS for a in TZ_REQUIRED.get(c, ())}
        counts = count_values(self._source.train_values(frozenset(attributes)), chosen)
        profiles = {n: profile_attribute(n, c) for n, c in counts.values.items()}
        entries = [e for n, p in profiles.items()
                   for e in attribute_entries(p, counts.values[n], LexiconConfig())]
        priors = category_priors(counts, profiles)
        self._logger.info("stand_lexicon", attributes=len(profiles), entries=len(entries))
        lexicon = Lexicon(profiles, entries, priors)
        examples = self._examples(RequiredAttributes(required, lexicon), lexicon, chosen, config)
        names = self._names.names()
        categories = [StandCategory(category_id=c, name=names.get(c, ("", ""))[0],
                                    path=names.get(c, ("", ""))[1]) for c in sorted(chosen)]
        twins = build_stand_twins(self._twin_rows, lexicon, required, chosen,
                                  config.twins_per_category) if self._twin_rows else []
        self._logger.info("stand_twins", entries=len(twins))
        pack = StandPack(built_at=now.isoformat(timespec="seconds"), threshold=config.threshold,
                         profiles=profiles, entries=entries, priors=priors, required=required,
                         categories=categories, examples=examples, twins=twins)
        size = self._sink.save(pack)
        self._logger.info("stand_pack_saved", bytes=size, examples=len(examples),
                          categories=len(categories))
        return size

    def _examples(self, required: RequiredAttributes, lexicon: Lexicon, chosen: frozenset[int],
                  config: StandPackConfig) -> list[StandExample]:
        quota = {c: config.focus_examples if c in FOCUS else config.other_examples for c in chosen}
        picked: list[StandExample] = []
        for batch in self._source.cards(frozenset({"test"}), 2000):
            for card in batch:
                if not wanted(card, quota, config):
                    continue
                extraction = extract_card(card, required, lexicon, config.threshold)
                if len(extraction.picks) >= 2 and extraction.review:
                    picked.append(example_of(card))
                    quota[card.category_id or 0] -= 1
            if len(picked) >= config.max_examples or not any(v > 0 for v in quota.values()):
                break
        return picked[: config.max_examples]


def choose_categories(records: Sequence[RequiredRecord], stats: Mapping[int, tuple[int, int]],
                      limit: int) -> frozenset[int]:
    known = {r.category_id for r in records}
    ranked = sorted(known, key=lambda c: -stats.get(c, (0, 0))[0])
    return frozenset(ranked[:limit]) | (frozenset(FOCUS) & known)


def count_values(rows: Iterable[TrainValue], chosen: frozenset[int]) -> Counts:
    values: dict[str, Counter[tuple[str, str | None]]] = defaultdict(Counter)
    per_category: dict[tuple[int, str], Counter[tuple[str, str | None]]] = defaultdict(Counter)
    for row in rows:
        pair = (row.value, row.unit)
        values[row.attribute][pair] += 1
        if row.category_id in chosen:
            per_category[(row.category_id, row.attribute)][pair] += 1
    return Counts(dict(values), dict(per_category))


def category_priors(counts: Counts, profiles: Mapping[str, AttributeProfile]
                    ) -> dict[tuple[int, str], dict[str, float]]:
    priors: dict[tuple[int, str], dict[str, float]] = {}
    for (category, attribute), counter in counts.per_category.items():
        numeric = profiles[attribute].numeric
        keys: Counter[str] = Counter()
        for (value, unit), count in counter.items():
            keys[canonical_key(value, unit, numeric)] += count
        total = sum(keys.values())
        priors[(category, attribute)] = {k: round(c / total, 6) for k, c in keys.items()}
    return priors


def wanted(card: CardRecord, quota: Mapping[int, int], config: StandPackConfig) -> bool:
    return (card.category_id is not None and quota.get(card.category_id, 0) > 0
            and bool(card.title) and len(card.description or "") >= config.min_description)


def example_of(card: CardRecord) -> StandExample:
    return StandExample(sku_id=card.sku_id, category_id=card.category_id or 0,
                        title=card.title or "", description=card.description or "",
                        seller_params=card.seller_params)

