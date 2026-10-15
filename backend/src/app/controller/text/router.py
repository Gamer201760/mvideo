from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.controller.errors import ErrorResponse
from app.controller.text.schemas import (
    CategoryCandidateSchema,
    ExtractTextRequest,
    ExtractTextResponse,
    TextTitleSchema,
    TextValueSchema,
)
from app.usecase.text_extract import ExtractText

router = APIRouter(tags=["text"])
ERRORS: dict[int | str, dict[str, object]] = {
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def text_usecase(request: Request) -> ExtractText:
    usecase: ExtractText = request.app.state.stand.text.extract
    return usecase


@router.post("/extract-text", response_model=ExtractTextResponse, responses=ERRORS)
async def extract_text(body: ExtractTextRequest,
                       usecase: Annotated[ExtractText, Depends(text_usecase)]
                       ) -> ExtractTextResponse:
    result = await usecase.execute(body.text)
    names = usecase.category_names()
    title = None
    if result.title is not None and result.title_source is not None:
        title = TextTitleSchema(value=result.title, source=result.title_source,
                                start=result.title_start, end=result.title_end)
    return ExtractTextResponse(
        text=result.text, category_id=result.category_id, category_name=result.category_name,
        category_confidence=result.category_confidence,
        candidates=[CategoryCandidateSchema(category_id=c, name=names.get(c), confidence=p)
                    for c, p in result.candidates],
        title=title,
        values=[TextValueSchema(
            attribute=v.attribute, value=v.value, confidence=v.confidence, source=v.source,
            sources=list(v.sources), evidence=v.evidence, start=v.start, end=v.end,
            text_start=v.text_start, text_end=v.text_end,
            status="review" if v.in_review else "accepted", review_id=v.review_id,
        ) for v in result.values],
        missing=list(result.missing), threshold=result.threshold, search=result.search,
    )
