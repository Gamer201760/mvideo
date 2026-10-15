import random
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.domain.category_guess import ClickMapping, resolve
from app.domain.category_metrics import histogram
from app.usecase.category_ports import (
    CategoryClassifier,
    CategoryCorpus,
    CategorySink,
    ClickVote,
)
from app.usecase.interface import Logger

SAMPLE_TEXT = 90
HISTOGRAM_BINS = 10


@dataclass(slots=True)
class ScanResult:
    cards: int = 0
    sources: Counter[str] = field(default_factory=Counter)
    pending: int = 0
    accepted: int = 0
    histogram: list[int] = field(default_factory=lambda: [0] * HISTOGRAM_BINS)
    samples: list[dict[str, object]] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        known = sum(self.sources.values())
        return {
            "cards": self.cards,
            "with_category": known,
            "by_source": dict(self.sources),
            "share_with_category": round(known / self.cards, 4) if self.cards else 0.0,
            "outside_catalog_without_clicks": self.pending,
            "classifier_accepted": self.accepted,
            "classifier_accepted_share": round(self.accepted / self.pending, 4)
            if self.pending else 0.0,
            "outside_catalog_max_probability_histogram": self.histogram,
            "samples": self.samples,
        }


def scan_cards(
    corpus: CategoryCorpus,
    classifier: CategoryClassifier,
    sink: CategorySink,
    logger: Logger,
    votes: Mapping[int, ClickVote],
    mapping: Mapping[int, ClickMapping],
    threshold: float,
    batch: int,
    top_k: int,
    sample_size: int,
    seed: int,
) -> ScanResult:
    names = corpus.category_names()
    rng = random.Random(seed)
    result = ScanResult()
    for cards in corpus.cards(batch):
        result.cards += len(cards)
        pending = [c for c in cards if c.catalog_category is None
                   and _mapped(votes.get(c.sku_id), mapping) is None]
        ranked = classifier.rank([c.text for c in pending], top_k)
        by_sku = {c.sku_id: r for c, r in zip(pending, ranked, strict=True)}
        tops = [r[0][1] for r in ranked if r]
        for i, count in enumerate(histogram(tops, HISTOGRAM_BINS)):
            result.histogram[i] += count
        for card, r in zip(pending, ranked, strict=True):
            result.pending += 1
            if not r:
                continue
            accepted = r[0][1] >= threshold
            result.accepted += accepted
            row: dict[str, object] = {
                "sku_id": card.sku_id, "text": card.text[:SAMPLE_TEXT],
                "category_id": r[0][0], "category": names.get(r[0][0], ""),
                "probability": round(r[0][1], 3), "accepted": accepted,
            }
            if len(result.samples) < sample_size:
                result.samples.append(row)
            elif (slot := rng.randrange(result.pending)) < sample_size:
                result.samples[slot] = row
        guesses = [g for c in cards if (g := resolve(
            c.sku_id, c.catalog_category, _mapped(votes.get(c.sku_id), mapping),
            by_sku.get(c.sku_id, ()), threshold)) is not None]
        result.sources.update(g.source.value for g in guesses)
        sink.write(guesses)
        logger.info("category_batch", cards=result.cards)
    sink.close()
    return result


def _mapped(vote: ClickVote | None, mapping: Mapping[int, ClickMapping]) -> ClickMapping | None:
    return mapping.get(vote.click_category) if vote is not None else None
