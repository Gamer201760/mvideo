from collections.abc import Sequence
from typing import Protocol

from app.domain.decision import Decision, DecisionRequest
from app.domain.inference import Completion, StructuredRequest, Vector

type LogValue = str | int | float | bool | None


class Logger(Protocol):
    def info(self, event: str, **fields: LogValue) -> None: ...

    def warning(self, event: str, **fields: LogValue) -> None: ...

    def error(
        self, event: str, *, exc: BaseException | None = None, **fields: LogValue
    ) -> None: ...


class LanguageModel(Protocol):
    async def complete(self, request: StructuredRequest) -> Completion: ...


class Embeddings(Protocol):
    async def embed_queries(self, texts: Sequence[str]) -> list[Vector]: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]: ...

    async def aclose(self) -> None: ...


class DecisionModel(Protocol):
    async def decide(self, request: DecisionRequest) -> Decision: ...

    async def aclose(self) -> None: ...
