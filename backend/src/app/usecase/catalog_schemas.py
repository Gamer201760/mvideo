from typing import Protocol

from app.domain.attribute_flow import CatalogCandidate


class CatalogSchemas(Protocol):
    def snapshot(self) -> tuple[CatalogCandidate, ...]: ...
