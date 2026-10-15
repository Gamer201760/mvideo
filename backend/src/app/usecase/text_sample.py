import heapq
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.synthetic_text import InputKind, SourceCard, render
from app.domain.values import display_value
from app.usecase.baseline_ports import CardRecord
from app.usecase.text_ports import TextCorpus

KINDS = tuple(InputKind)
NOISE_CARDS = 3
SCAN_BATCH = 20_000


@dataclass(frozen=True, slots=True)
class SampledCard:
    card: CardRecord
    gold: Mapping[str, tuple[str, str | None]]

    def source(self) -> SourceCard:
        return SourceCard(self.card.title or "", self.card.description or "",
                          self.card.seller_params)


def order(sku_id: int, seed: int) -> int:
    return (sku_id * 2654435761 + seed * 40503) % (1 << 32)


def sample_cards(corpus: TextCorpus, split: str, categories: frozenset[int] | None,
                 per_category: int, limit: int, seed: int) -> list[CardRecord]:
    kept: dict[int, list[tuple[int, int, CardRecord]]] = {}
    for batch in corpus.cards(frozenset({split}), SCAN_BATCH):
        for card in batch:
            if card.category_id is None or not card.title or not card.description:
                continue
            if categories is not None and card.category_id not in categories:
                continue
            heap = kept.setdefault(card.category_id, [])
            item = (-order(card.sku_id, seed), card.sku_id, card)
            if len(heap) < per_category:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    cards = sorted((c for heap in kept.values() for _, _, c in heap),
                   key=lambda c: order(c.sku_id, seed))
    return cards[:limit]


def attach_gold(corpus: TextCorpus, cards: Sequence[CardRecord], split: frozenset[str],
                attributes: frozenset[str]) -> list[SampledCard]:
    wanted = {c.sku_id for c in cards}
    gold: dict[int, dict[str, tuple[str, str | None]]] = {}
    for rows in corpus.gold_rows(split, attributes):
        for sku, attribute, value, unit in rows:
            if sku in wanted:
                gold.setdefault(sku, {})[attribute] = (value, unit)
    return [SampledCard(c, gold.get(c.sku_id, {})) for c in cards]


def gold_display(gold: Mapping[str, tuple[str, str | None]]) -> dict[str, str]:
    return {a: display_value(v, u) for a, (v, u) in gold.items()}


def synthetic_inputs(cards: Sequence[SampledCard], seed: int,
                     kinds: Sequence[InputKind] = KINDS) -> list[tuple[SampledCard, InputKind, str]]:
    rng = random.Random(seed)
    inputs = []
    for position, sampled in enumerate(cards):
        others = [cards[(position + step) % len(cards)].source()
                  for step in range(1, NOISE_CARDS + 1) if len(cards) > step]
        for kind in kinds:
            inputs.append((sampled, kind, render(kind, sampled.source(), others, rng)))
    return inputs
