from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.review import ReviewAction, ReviewStatus


class SellerParamSchema(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=500)
    unit: str | None = Field(default=None, max_length=50)


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


class ExtractRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20000)
    seller_params: list[SellerParamSchema] = Field(default_factory=list, max_length=200)
    category_id: int | None = None


class ExtractedValueSchema(BaseModel):
    attribute: str
    value: str
    confidence: float
    source: str
    sources: list[str]
    evidence: str
    start: int
    end: int
    status: Literal["accepted", "review"]
    review_id: str | None


class ExtractResponse(BaseModel):
    text: str
    threshold: float
    values: list[ExtractedValueSchema]
    missing: list[str]


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


class ResolveRequest(BaseModel):
    action: ReviewAction
    value: str | None = Field(default=None, max_length=500)
