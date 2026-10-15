from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

import pyarrow.parquet as pq


class ParquetCategoryTree:
    def __init__(self, processed: Path) -> None:
        table = pq.read_table(processed / "categories.parquet",
                              columns=["category_id", "parent_id", "path"])
        self._parent: dict[int, int] = {}
        self._children: dict[int, list[int]] = defaultdict(list)
        self._names: dict[int, str] = {}
        for category, parent, path in zip(table["category_id"].to_pylist(),
                                          table["parent_id"].to_pylist(),
                                          table["path"].to_pylist(), strict=True):
            if path:
                self._names[category] = path
            if parent is not None:
                self._parent[category] = parent
                self._children[parent].append(category)

    def parent(self, category: int) -> int | None:
        return self._parent.get(category)

    def children(self, category: int) -> Sequence[int]:
        return self._children.get(category, [])

    def names(self) -> Mapping[int, str]:
        return self._names
