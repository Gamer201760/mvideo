from collections import defaultdict
from collections.abc import Mapping, Sequence

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.adapter.dataset.baseline_source import GOLD_BATCH, ParquetBaselineSource
from app.usecase.baseline_ports import GoldRecord


class ParquetRankerSource(ParquetBaselineSource):
    def gold_where(
        self, splits: frozenset[str], attributes: frozenset[str], modulo: int
    ) -> Mapping[int, Sequence[GoldRecord]]:
        skus = pa.array([s for s, name in self._split_map().items()
                         if name in splits and s % modulo == 0], type=pa.int64())
        wanted = pa.array(sorted(attributes), type=pa.string())
        result: dict[int, list[GoldRecord]] = defaultdict(list)
        gold = pq.ParquetFile(self._dir / "gold.parquet")
        for batch in gold.iter_batches(batch_size=GOLD_BATCH):
            mask = pc.and_(pc.is_in(batch.column(0), value_set=skus),
                           pc.is_in(batch.column(1), value_set=wanted))
            kept = batch.filter(mask)
            for sku, attribute, value, unit in zip(*(kept.column(i).to_pylist() for i in range(4)),
                                                   strict=True):
                result[sku].append(GoldRecord(attribute, value, unit))
        return result
