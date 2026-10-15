from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.controller.errors import ErrorResponse
from app.controller.stand.schemas import (
    CategorySchema,
    ExampleSchema,
    ExamplesResponse,
    ExtractedValueSchema,
    ExtractRequest,
    ExtractResponse,
    ResolveRequest,
    ReviewItemSchema,
    ReviewListResponse,
    SellerParamSchema,
    StandInfoResponse,
)
from app.domain.card_text import SellerParam
from app.domain.review import ReviewItem, ReviewStatus
from app.usecase.extract_card import ExtractCard
from app.usecase.review_queue import ReviewQueue
from app.usecase.stand_catalog import StandCatalog
from app.usecase.stand_ports import CardInput

router = APIRouter(tags=["stand"])
ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def extract_usecase(request: Request) -> ExtractCard:
    usecase: ExtractCard = request.app.state.stand.extract
    return usecase


def review_usecase(request: Request) -> ReviewQueue:
    usecase: ReviewQueue = request.app.state.stand.review
    return usecase


def catalog_usecase(request: Request) -> StandCatalog:
    usecase: StandCatalog = request.app.state.stand.catalog
    return usecase


@router.get("/stand", response_model=StandInfoResponse, responses=ERRORS)
async def stand_info(catalog: Annotated[StandCatalog, Depends(catalog_usecase)]
                     ) -> StandInfoResponse:
    info = catalog.info()
    return StandInfoResponse(
        built_at=info.built_at, threshold=info.threshold,
        categories=[CategorySchema(category_id=c.category_id, name=c.name, path=c.path,
                                   attributes=list(c.attributes)) for c in info.categories],
    )


@router.get("/examples", response_model=ExamplesResponse, responses=ERRORS)
async def examples(catalog: Annotated[StandCatalog, Depends(catalog_usecase)]
                   ) -> ExamplesResponse:
    return ExamplesResponse(items=[
        ExampleSchema(sku_id=e.sku_id, category_id=e.category_id, title=e.title,
                      description=e.description,
                      seller_params=[SellerParamSchema(name=p.name, value=p.value, unit=p.unit)
                                     for p in e.seller_params])
        for e in catalog.examples()
    ])


@router.post("/extract", response_model=ExtractResponse, responses=ERRORS)
async def extract(body: ExtractRequest,
                  usecase: Annotated[ExtractCard, Depends(extract_usecase)]) -> ExtractResponse:
    card = CardInput(
        title=body.title, description=body.description, category_id=body.category_id,
        seller_params=tuple(SellerParam(p.name, p.value, p.unit) for p in body.seller_params),
    )
    result = await usecase.execute(card)
    return ExtractResponse(
        text=result.text, threshold=result.threshold, missing=list(result.missing),
        values=[ExtractedValueSchema(
            attribute=v.attribute, value=v.value, confidence=v.confidence,
            source=v.source, sources=list(v.sources), evidence=v.evidence, start=v.start, end=v.end,
            status="review" if v.in_review else "accepted", review_id=v.review_id,
        ) for v in result.values],
    )


@router.get("/review", response_model=ReviewListResponse, responses=ERRORS)
async def review_list(usecase: Annotated[ReviewQueue, Depends(review_usecase)],
                      status: Annotated[ReviewStatus | None, Query()] = None
                      ) -> ReviewListResponse:
    return ReviewListResponse(items=[_item(i) for i in await usecase.list(status)])


@router.post("/review/{item_id}", response_model=ReviewItemSchema, responses=ERRORS)
async def review_resolve(item_id: str, body: ResolveRequest,
                         usecase: Annotated[ReviewQueue, Depends(review_usecase)]
                         ) -> ReviewItemSchema:
    return _item(await usecase.resolve(item_id, body.action, body.value))


def _item(item: ReviewItem) -> ReviewItemSchema:
    return ReviewItemSchema(
        id=item.id, category_id=item.category_id, title=item.title, attribute=item.attribute,
        value=item.value, confidence=item.confidence, source=item.source,
        evidence=item.evidence, status=item.status, resolved_value=item.resolved_value,
        created_at=item.created_at, resolved_at=item.resolved_at,
    )
