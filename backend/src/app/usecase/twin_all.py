import time
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.profile import BRAND
from app.domain.twin import Transfer, TwinQuery, accepted, others, title_numbers, twin_title, vote
from app.domain.values import canonical_key
from app.usecase.baseline_ports import CardRecord
from app.usecase.interface import Logger
from app.usecase.ranker_ports import Calibrator
from app.usecase.twin_ports import TitleIndex
from app.usecase.twins import TwinModel

Raw = Mapping[str, object]
Scored = Mapping[str, tuple[Transfer, float]]


@dataclass(frozen=True, slots=True)
class CardTransfers:
    sku_id: int
    transfers: Scored


class ShardCardsSource(Protocol):
    def shards(self) -> Sequence[str]: ...

    def cards(self, shard: str, batch: int) -> Iterator[list[CardRecord]]: ...

    def stage(self, shard: str) -> Iterator[Raw]: ...


class ShardTransferSink(Protocol):
    def open(self, shard: str) -> None: ...

    def write(self, records: Sequence[CardTransfers]) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _Request:
    card: CardRecord
    query: TwinQuery
    slots: list[str]


def _category(stage: Raw) -> int | None:
    value = stage.get("category_id")
    return int(str(value)) if value is not None else None


def _attributes(stage: Raw) -> Mapping[str, Mapping[str, object]]:
    section = stage.get("attributes")
    return section if isinstance(section, Mapping) else {}


def request_of(card: CardRecord, stage: Raw, model: TwinModel) -> _Request | None:
    title = twin_title(card.title)
    if not title:
        return None
    picked = _attributes(stage)
    profiles = model.context.required.profiles(_category(stage))
    slots = [name for name in profiles if name not in picked]
    if not slots:
        return None
    brand = picked.get(BRAND)
    brand_key = canonical_key(str(brand.get("value", "")), None, False) if brand else None
    return _Request(card, TwinQuery(title, title_numbers(title), brand_key or None), slots)


class TransferAllCards:
    def __init__(
        self, source: ShardCardsSource, index: TitleIndex, calibrator: Calibrator,
        sink: ShardTransferSink, logger: Logger,
    ) -> None:
        self._source = source
        self._index = index
        self._calibrator = calibrator
        self._sink = sink
        self._logger = logger

    def run(self, model: TwinModel, k: int, floor: float, batch: int) -> dict[str, object]:
        started = time.monotonic()
        tally: Counter[str] = Counter()
        for shard in self._source.shards():
            self._sink.open(shard)
            stages = self._source.stage(shard)
            for cards in self._source.cards(shard, batch):
                records = self._batch(cards, stages, model, k, floor, tally)
                self._sink.write(records)
                self._logger.info("twins_all_batch", shard=shard, cards=tally["cards"])
            if next(stages, None) is not None:
                raise ValueError(f"shard {shard}: more stage records than cards")
            self._sink.close()
        return {"cards": tally["cards"], "queried": tally["queried"],
                "cards_with_transfer": tally["with_transfer"], "transfers": tally["transfers"],
                "threshold": model.threshold, "seconds": round(time.monotonic() - started, 1)}

    def _batch(
        self, cards: list[CardRecord], stages: Iterator[Raw], model: TwinModel, k: int,
        floor: float, tally: Counter[str],
    ) -> list[CardTransfers]:
        requests: list[_Request | None] = []
        for card in cards:
            stage = next(stages, None)
            if stage is None or int(str(stage.get("sku_id"))) != card.sku_id:
                raise ValueError(f"stage records are out of order at sku {card.sku_id}")
            requests.append(request_of(card, stage, model))
        asked = [r for r in requests if r is not None]
        found = iter(self._index.neighbors([r.query.title for r in asked], k))
        entries = model.context.data.entries
        records = []
        for card, request in zip(cards, requests, strict=True):
            scored: dict[str, tuple[Transfer, float]] = {}
            if request is not None:
                near = others([(entries[i], s) for i, s in next(found)], card.sku_id)
                kept = accepted(vote(request.query, near, request.slots, floor), model.threshold)
                confidences = self._calibrator.transform([t.similarity for t in kept.values()]) \
                    if kept else []
                scored = {n: (t, round(float(c), 4))
                          for (n, t), c in zip(kept.items(), confidences, strict=True)}
            records.append(CardTransfers(card.sku_id, scored))
            tally["cards"] += 1
            tally["queried"] += request is not None
            tally["with_transfer"] += bool(scored)
            tally["transfers"] += len(scored)
        return records
