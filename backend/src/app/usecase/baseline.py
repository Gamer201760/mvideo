import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.candidate import best_attributes
from app.domain.extractors import MIN_AFFINITY
from app.domain.metrics import MetricsBook, Observation, value_in_text
from app.domain.profile import TZ_REQUIRED
from app.domain.values import canonical_key
from app.usecase.baseline_ports import (
    BaselineSource,
    CardRecord,
    GoldRecord,
    PredictionSink,
    ReportSink,
)
from app.usecase.extraction import (
    UNKNOWN_CATEGORY_ATTRIBUTES,
    CardExtraction,
    RequiredAttributes,
    candidate_rows,
    extract_card,
    prediction_of,
)
from app.usecase.interface import Logger
from app.usecase.lexicon_builder import LexiconConfig, build_lexicon
from app.usecase.report import build_report, render_markdown

EVAL_SPLITS = frozenset({"test", "new_category"})
FOCUS_CATEGORIES = {761: "smartphones", 987: "laptops"}


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    splits: frozenset[str] | None = EVAL_SPLITS
    evaluate: bool = True
    batch: int = 2000
    min_confidence: float = 0.35
    head_categories: int = 50
    large_seller: int = 1000
    small_seller: int = 100
    lexicon: LexiconConfig = field(default_factory=LexiconConfig)


@dataclass(slots=True)
class Segments:
    head: frozenset[int]
    seller_cards: Mapping[str, int]
    config: BaselineConfig
    category_cards: Mapping[int, int]

    def pair_weight(self, category: int | None, weight: float) -> float:
        if category is None:
            return 0.0
        return weight / self.category_cards.get(category, 1)

    def of(self, card: CardRecord) -> list[str]:
        groups = ["all", f"split:{card.split}"]
        if card.category_id is not None:
            groups.append("categories:head" if card.category_id in self.head else "categories:tail")
            focus = FOCUS_CATEGORIES.get(card.category_id)
            if focus:
                groups.append(f"category:{focus}")
        size = self.seller_cards.get(card.seller or "", 0)
        if size >= self.config.large_seller:
            groups.append("sellers:large")
        elif size < self.config.small_seller:
            groups.append("sellers:small")
        else:
            groups.append("sellers:medium")
        return groups


class RunBaseline:
    def __init__(
        self, source: BaselineSource, sink: PredictionSink, reports: ReportSink, logger: Logger
    ) -> None:
        self._source = source
        self._sink = sink
        self._reports = reports
        self._logger = logger

    def run(self, config: BaselineConfig) -> Mapping[str, object]:
        started = time.monotonic()
        records = self._source.required()
        names = frozenset(r.attribute for r in records) | extra_attributes()
        lexicon = build_lexicon(self._source.train_values(names), config.lexicon)
        required = RequiredAttributes(records, lexicon)
        self._logger.info("lexicon_built", attributes=len(lexicon.profiles), entries=lexicon.size)
        gold = self._source.gold(config.splits) if config.evaluate and config.splits else {}
        stats = self._source.category_stats()
        head = frozenset(sorted(stats, key=lambda c: -stats[c][0])[: config.head_categories])
        cards_of = {c: max(1, s[1]) for c, s in stats.items()}
        segments = Segments(head, self._source.seller_cards(), config, cards_of)
        plain, weighted = MetricsBook(weighted=False), MetricsBook(weighted=True)
        cards = 0
        for batch in self._source.cards(config.splits, config.batch):
            predictions, rows = [], []
            for card in batch:
                extraction = extract_card(card, required, lexicon, config.min_confidence)
                predictions.append(prediction_of(card, extraction))
                rows.extend(candidate_rows(card, extraction))
                if config.evaluate:
                    observe(card, extraction, gold.get(card.sku_id, ()), required, segments,
                            (plain, weighted))
            self._sink.write(predictions, rows)
            cards += len(batch)
            self._logger.info("batch_done", cards=cards)
        self._sink.close()
        elapsed = round(time.monotonic() - started, 1)
        report = build_report(plain, weighted, cards=cards, lexicon_entries=lexicon.size,
                              attributes=len(lexicon.profiles))
        if config.evaluate:
            self._reports.write(report, render_markdown(report))
        self._logger.info("baseline_done", cards=cards, seconds=elapsed)
        return report


def observe(
    card: CardRecord, extraction: CardExtraction, gold: Sequence[GoldRecord],
    required: RequiredAttributes, segments: Segments, books: tuple[MetricsBook, MetricsBook],
    extra_groups: Sequence[str] = (),
) -> None:
    by_attribute = {g.attribute: g for g in gold}
    seller_names = [p.name for p in card.seller_params]
    groups = [*segments.of(card), *extra_groups]
    weights = required.weights(card.category_id)
    for name, profile in extraction.profiles.items():
        truth = by_attribute.get(name)
        pick = extraction.picks.get(name)
        correct = False
        reachable = False
        if truth is not None:
            expected = canonical_key(truth.value, truth.unit, profile.numeric)
            correct = pick is not None and pick.candidate.key == expected
            reachable = value_in_text(extraction.text, truth.value, truth.unit, profile)
        filled = any(name in best_attributes(extraction.profiles, s, MIN_AFFINITY)
                     for s in seller_names)
        weight = segments.pair_weight(card.category_id, weights.get(name, 1.0))
        observation = Observation(name, truth is not None, pick is not None, correct, reachable,
                                  filled, weight)
        for book in books:
            book.add(groups, observation)


def extra_attributes() -> frozenset[str]:
    names = {a for attributes in TZ_REQUIRED.values() for a in attributes}
    return frozenset(names | set(UNKNOWN_CATEGORY_ATTRIBUTES))
