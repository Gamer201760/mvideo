from collections.abc import Mapping, Sequence
from typing import Protocol

from app.domain.decision import Decision


class DecisionCache(Protocol):
    def get(self, fingerprint: str) -> Decision | None: ...

    def put(self, fingerprint: str, decision: Decision) -> None: ...


class CategoryTree(Protocol):
    def parent(self, category: int) -> int | None: ...

    def children(self, category: int) -> Sequence[int]: ...

    def names(self) -> Mapping[int, str]: ...
