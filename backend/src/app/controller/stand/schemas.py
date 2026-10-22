from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.review import ReviewAction, ReviewStatus


class SellerParamSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=500)
    unit: str | None = Field(default=None, max_length=50)

    @field_validator("name")
    @classmethod
    def exclude_gold(cls, value: str) -> str:
        if value.strip().casefold().endswith("_search"):
            raise ValueError("Catalog gold is not card input")
        return value.strip()


class CategorySchema(BaseModel):
    category_id: int
    name: str
    path: str
    attributes: list[str]


class StandInfoResponse(BaseModel):
    built_at: str
    threshold: float
    categories: list[CategorySchema]


class ExampleSchema(BaseModel):
    sku_id: int
    category_id: int
    title: str
    description: str
    seller_params: list[SellerParamSchema]


class ExamplesResponse(BaseModel):
    items: list[ExampleSchema]


class CategoryPreviewResponse(BaseModel):
    candidates: list[CategorySchema]


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: Literal["rules", "hybrid"] = "rules"
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20000)
    seller_params: list[SellerParamSchema] = Field(default_factory=list, max_length=200)
    category_id: int | None = None

    @model_validator(mode="after")
    def bound_text(self) -> "ExtractRequest":
        size = (
            len(self.title)
            + len(self.description)
            + sum(len(p.name) + len(p.value) + len(p.unit or "") for p in self.seller_params)
        )
        if size > 24000 or not self.title.strip():
            raise ValueError("Card exceeds the input limit or has an empty title")
        return self


class AttributeRiskSchema(BaseModel):
    level: Literal["low", "medium", "high"]
    score: float = Field(ge=0, le=1)
    reasons: list[str]
    method: Literal["heuristic", "catalog_proxy"]


class ExtractedValueSchema(BaseModel):
    attribute: str
    value: str
    confidence: float | None
    risk: AttributeRiskSchema | None = None
    source: str
    sources: list[str]
    evidence: str
    start: int
    end: int
    status: Literal["accepted", "review", "unverified"]
    review_id: str | None
    acceptance: Literal["automatic", "manual", "review"] | None = None


class EvidenceRejectionSchema(BaseModel):
    attribute: str
    reason: str
    evidence: str


class ExtractResponse(BaseModel):
    text: str
    threshold: float | None
    engine: Literal["rules", "hybrid"] = "rules"
    category: CategorySchema | None = None
    extra_values: list[ExtractedValueSchema] = Field(default_factory=list)
    values: list[ExtractedValueSchema]
    missing: list[str]
    rejections: list[EvidenceRejectionSchema] = Field(default_factory=list)
    auto_accept_enabled: bool = False
    fallback_reason: str | None = None


class ReviewItemSchema(BaseModel):
    id: str
    category_id: int | None
    title: str
    attribute: str
    value: str
    confidence: float
    source: str
    evidence: str
    status: ReviewStatus
    resolved_value: str | None
    created_at: datetime
    resolved_at: datetime | None


class ReviewListResponse(BaseModel):
    items: list[ReviewItemSchema]
    total: int


class CardReviewResponse(BaseModel):
    card_key: str
    items: list[ReviewItemSchema]


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: ReviewAction
    value: str | None = Field(default=None, max_length=500)
    override: bool = False
    expected_value: str | None = Field(default=None, max_length=500)


class AddReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card: ExtractRequest
    attribute: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=500)
    evidence: str = Field(min_length=1, max_length=24000)


class RunSummarySchema(BaseModel):
    id: str
    title: str
    engine: Literal["rules", "hybrid"]
    status: Literal["running", "completed", "failed", "interrupted"]
    started_at: datetime
    finished_at: datetime | None


class RunListResponse(BaseModel):
    items: list[RunSummarySchema]
    total: int


class RunDetailResponse(BaseModel):
    input: ExtractRequest
    result: ExtractResponse | None
    status: Literal["running", "completed", "failed", "interrupted"]
