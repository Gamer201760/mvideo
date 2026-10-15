import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Protocol

from app.domain.fusion import BASELINE, DECISION, NEW, RANKER, TWIN, FusionRules, resolve
from app.domain.twin import TWIN_SOURCE
from app.usecase.baseline_ports import CardRecord
from app.usecase.final_options import DECISION_MARK, card_mode
from app.usecase.interface import Logger

Raw = Mapping[str, object]
Values = Mapping[str, Mapping[str, object]]


class AllCardsSource(Protocol):
    def pairs(self) -> Iterator[tuple[Raw, Raw, Raw | None]]: ...

    def records(self, name: str) -> Mapping[int, Raw]: ...


class RecordSink(Protocol):
    def write(self, records: Sequence[Raw]) -> None: ...

    def close(self) -> None: ...


def _values(record: Raw | None, key: str = "attributes") -> Values:
    if record is None:
        return {}
    section = record.get(key)
    return section if isinstance(section, Mapping) else {}


def _sources(value: Mapping[str, object]) -> list[str]:
    raw = value.get("sources")
    return [str(s) for s in raw] if isinstance(raw, list) else []


def card_options(
    ranker: Raw, baseline: Raw, decision: Raw | None, twin: Raw | None
) -> dict[str, dict[str, Mapping[str, object] | None]]:
    by_source: dict[str, dict[str, Mapping[str, object] | None]] = {
        BASELINE: dict(_values(baseline)),
        RANKER: dict(_values(ranker)),
        TWIN: {n: v for n, v in _values(twin).items() if v.get("source") == TWIN_SOURCE},
    }
    if decision is not None:
        decided = _values(decision)
        chosen: dict[str, Mapping[str, object] | None] = {
            n: v for n, v in decided.items() if DECISION_MARK in _sources(v)}
        chosen.update({n: None for n in by_source[BASELINE] if n not in decided})
        by_source[DECISION] = chosen
    options: dict[str, dict[str, Mapping[str, object] | None]] = {}
    for source, values in by_source.items():
        for name, value in values.items():
            options.setdefault(name, {})[source] = value
    return options


def _mode(record: Raw) -> str:
    category = record.get("category_id")
    split = record.get("split")
    card = CardRecord(0, int(str(category)) if category is not None else None, None, None, None,
                      (), str(split) if split is not None else None)
    return card_mode(card)


def fuse_record(
    ranker: Raw, baseline: Raw, decision: Raw | None, twin: Raw | None, rules: FusionRules,
    calibrate: Callable[[str, float], float], threshold: float, used: Counter[str],
) -> dict[str, object]:
    mode = _mode(ranker)
    attributes: dict[str, object] = {}
    review: dict[str, object] = dict(_values(ranker, "review"))
    for name, options in card_options(ranker, baseline, decision, twin).items():
        keys = {s: (str(v.get("value")) if v is not None else None) for s, v in options.items()}
        source = resolve(keys, rules.rule(name, mode))
        value = options.get(source) if source is not None else None
        if source is None or value is None:
            continue
        confidence = calibrate(source, float(str(value.get("confidence", 0.0))))
        fused = {**value, "confidence": confidence, "stage": source}
        if confidence >= threshold:
            attributes[name] = fused
            review.pop(name, None)
            used[source] += 1
        else:
            review[name] = fused
            used["review"] += 1
    return {"sku_id": ranker.get("sku_id"), "category_id": ranker.get("category_id"),
            "split": ranker.get("split"), "category_mode": mode,
            "confidence_calibrated": True, "attributes": attributes, "review": review}


class FuseAllCards:
    def __init__(self, source: AllCardsSource, sink: RecordSink, logger: Logger) -> None:
        self._source = source
        self._sink = sink
        self._logger = logger

    def run(
        self, rules: FusionRules, calibrate: Callable[[str, float], float], threshold: float,
        decision: str, twins: str, batch: int = 5000,
    ) -> dict[str, object]:
        started = time.monotonic()
        decided, twin = self._source.records(decision), self._source.records(twins)
        used: Counter[str] = Counter()
        cards = empty = new = 0
        buffer: list[Raw] = []
        streamed = 0
        for ranker, baseline, shard_twin in self._source.pairs():
            sku = int(str(ranker.get("sku_id")))
            streamed += 1 if shard_twin is not None else 0
            record = fuse_record(ranker, baseline, decided.get(sku),
                                 shard_twin if shard_twin is not None else twin.get(sku), rules,
                                 calibrate, threshold, used)
            cards += 1
            empty += 0 if record["attributes"] else 1
            new += 1 if record["category_mode"] == NEW else 0
            buffer.append(record)
            if len(buffer) >= batch:
                self._sink.write(buffer)
                buffer = []
                self._logger.info("final_all_batch", cards=cards)
        self._sink.write(buffer)
        self._sink.close()
        return {"cards": cards, "without_attributes": empty, "new_or_unknown_category": new,
                "values_by_source": dict(used), "decision_cards": len(decided),
                "twin_cards": streamed or len(twin),
                "seconds": round(time.monotonic() - started, 1)}
