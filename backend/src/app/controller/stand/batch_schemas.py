from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.controller.errors import ErrorResponse
from app.controller.stand.schemas import ExtractRequest, ExtractResponse


class BatchCardRequest(ExtractRequest):
    id: str = Field(min_length=1, max_length=100)
    engine: Literal["hybrid"] = "hybrid"


class BatchExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[BatchCardRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bound_batch(self) -> "BatchExtractRequest":
        if len({card.id for card in self.items}) != len(self.items):
            raise ValueError("Batch card identifiers must be unique")
        size = sum(
            len(card.title)
            + len(card.description)
            + sum(len(p.name) + len(p.value) + len(p.unit or "") for p in card.seller_params)
            for card in self.items
        )
        if size > 240_000:
            raise ValueError("Batch exceeds the total input limit")
        return self


class BatchItemResponse(BaseModel):
    id: str
    run_id: str
    status: Literal["completed", "failed"]
    result: ExtractResponse | None
    error: ErrorResponse | None


class BatchSummary(BaseModel):
    requested: int
    succeeded: int
    failed: int
    provider_requests: int
    provider_cards: int
    rules_only_cards: int
    input_tokens: int | None
    output_tokens: int | None
    elapsed_ms: float
    provider: Literal["gateway", "local_rules"]


class BatchExtractResponse(BaseModel):
    items: list[BatchItemResponse]
    summary: BatchSummary
