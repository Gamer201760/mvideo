from typing import Literal

from pydantic import BaseModel, Field


class ExtractTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


class CategoryCandidateSchema(BaseModel):
    category_id: int
    name: str | None
    confidence: float


class TextValueSchema(BaseModel):
    attribute: str
    value: str
    confidence: float
    source: str
    sources: list[str]
    evidence: str
    start: int
    end: int
    text_start: int
    text_end: int
    status: Literal["accepted", "review"]
    review_id: str | None


class TextTitleSchema(BaseModel):
    value: str
    source: str
    start: int
    end: int


class ExtractTextResponse(BaseModel):
    text: str
    category_id: int | None
    category_name: str | None
    category_confidence: float
    candidates: list[CategoryCandidateSchema]
    title: TextTitleSchema | None
    values: list[TextValueSchema]
    missing: list[str]
    threshold: float
    search: str
