from collections.abc import Iterator, Mapping, Sequence

import pytest
from test_twins import (
    PHONE,
    FakeIndex,
    FakeSource,
    Identity,
    MemoryReports,
    MemorySink,
    SilentLogger,
)

from app.domain.twin import TwinEntry, others
from app.usecase.baseline_ports import CardRecord
from app.usecase.twin_all import CardTransfers, TransferAllCards
from app.usecase.twins import RunTwins, TwinConfig, TwinModel

TITLE = "Смартфон Samsung Galaxy A55 8/256GB"
SHARD = [CardRecord(10, PHONE, "ИП", TITLE, "", (), "train"),
         CardRecord(40, PHONE, "ООО", TITLE, "", (), None),
         CardRecord(41, PHONE, "ООО", "", "", (), None)]


def _stage(sku: int) -> dict[str, object]:
    brand = {"value": "Samsung", "confidence": 0.9, "source": "title_model"}
    return {"sku_id": sku, "category_id": PHONE, "attributes": {"Бренд": brand}}


class ShardSource:
    def __init__(self, stages: list[dict[str, object]]) -> None:
        self._stages = stages

    def shards(self) -> Sequence[str]:
        return ["0"]

    def cards(self, shard: str, batch: int) -> Iterator[list[CardRecord]]:
        yield SHARD

    def stage(self, shard: str) -> Iterator[Mapping[str, object]]:
        yield from self._stages


class MemoryShardSink:
    def __init__(self) -> None:
        self.records: list[CardTransfers] = []
        self.opened: list[str] = []

    def open(self, shard: str) -> None:
        self.opened.append(shard)

    def write(self, records: Sequence[CardTransfers]) -> None:
        self.records.extend(records)

    def close(self) -> None: ...


def _prepared(index: FakeIndex) -> TwinModel:
    usecase = RunTwins(FakeSource(), index, Identity(), MemorySink(), MemoryReports(),
                       SilentLogger())
    return usecase.prepare(TwinConfig(k=5))


def test_others_drops_the_card_itself() -> None:
    entry = TwinEntry(10, TITLE, frozenset(), "samsung", "a55", {})
    assert others([(entry, 1.0)], 10) == []
    assert others([(entry, 1.0)], 40) == [(entry, 1.0)]


def test_card_never_becomes_its_own_twin() -> None:
    index = FakeIndex()
    model = _prepared(index)
    sink = MemoryShardSink()
    summary = TransferAllCards(ShardSource([_stage(s.sku_id) for s in SHARD]), index, Identity(),
                               sink, SilentLogger()).run(model, 5, 0.5, 100)
    by_sku = {r.sku_id: r.transfers for r in sink.records}
    assert [r.sku_id for r in sink.records] == [10, 40, 41]
    assert by_sku[10] == {}
    transfer, confidence = by_sku[40]["Вес"]
    assert transfer.twin_sku == 10 and transfer.key == "190"
    assert confidence == transfer.similarity
    assert by_sku[41] == {}
    assert summary["cards"] == 3 and summary["cards_with_transfer"] == 1


def test_stage_records_must_follow_card_order() -> None:
    index = FakeIndex()
    model = _prepared(index)
    stages = [_stage(40), _stage(10), _stage(41)]
    usecase = TransferAllCards(ShardSource(stages), index, Identity(), MemoryShardSink(),
                               SilentLogger())
    with pytest.raises(ValueError, match="out of order"):
        usecase.run(model, 5, 0.5, 100)
