from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.controller.stand.dependencies import ERRORS, history_usecase
from app.controller.stand.flow_response import flow_response
from app.controller.stand.schemas import (
    CategoryPreviewResponse,
    CategorySchema,
    ExampleSchema,
    ExamplesResponse,
    ExtractedValueSchema,
    ExtractRequest,
    ExtractResponse,
    SellerParamSchema,
    StandInfoResponse,
)
from app.domain.card_text import SellerParam
from app.domain.errors import ModelFailure
from app.usecase.extract_card import ExtractCard
from app.usecase.review_card import ReviewCard
from app.usecase.run_history import RunHistory
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_catalog import StandCatalog
from app.usecase.stand_ports import CardInput

router = APIRouter(tags=["stand"])


def extract_usecase(request: Request) -> ExtractCard:
    usecase: ExtractCard = request.app.state.stand.extract
    return usecase


def flow_usecase(request: Request) -> StandAttributeFlow | None:
    usecase: StandAttributeFlow | None = request.app.state.stand.flow
    return usecase


def catalog_usecase(request: Request) -> StandCatalog:
    usecase: StandCatalog = request.app.state.stand.catalog
    return usecase


@router.get("/stand", response_model=StandInfoResponse, responses=ERRORS)
async def stand_info(
    catalog: Annotated[StandCatalog, Depends(catalog_usecase)],
) -> StandInfoResponse:
    info = catalog.info()
    return StandInfoResponse(
        built_at=info.built_at,
        threshold=info.threshold,
        categories=[
            CategorySchema(
                category_id=c.category_id, name=c.name, path=c.path, attributes=list(c.attributes)
            )
            for c in info.categories
        ],
    )


@router.get("/examples", response_model=ExamplesResponse, responses=ERRORS)
async def examples(catalog: Annotated[StandCatalog, Depends(catalog_usecase)]) -> ExamplesResponse:
    return ExamplesResponse(
        items=[
            ExampleSchema(
                sku_id=e.sku_id,
                category_id=e.category_id,
                title=e.title,
                description=e.description,
                seller_params=[
                    SellerParamSchema(name=p.name, value=p.value, unit=p.unit)
                    for p in e.seller_params
                ],
            )
            for e in catalog.examples()
        ]
    )


@router.post("/extract/preview", response_model=CategoryPreviewResponse, responses=ERRORS)
async def preview(
    body: ExtractRequest,
    flow: Annotated[StandAttributeFlow | None, Depends(flow_usecase)],
) -> CategoryPreviewResponse:
    if flow is None:
        raise ModelFailure("Hybrid attribute flow is not enabled")
    card = CardInput(
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        seller_params=tuple(SellerParam(p.name, p.value, p.unit) for p in body.seller_params),
    )
    prepared = await flow.prepare(card, limit=5)
    return CategoryPreviewResponse(
        candidates=[
            CategorySchema(
                category_id=c.category_id,
                name=c.path.split("/")[-1].strip(),
                path=c.path,
                attributes=[f.attribute for f in c.fields],
            )
            for c in prepared.candidates
        ]
    )


@router.post("/extract", response_model=ExtractResponse, responses=ERRORS)
async def extract(
    body: ExtractRequest,
    usecase: Annotated[ExtractCard, Depends(extract_usecase)],
    flow: Annotated[StandAttributeFlow | None, Depends(flow_usecase)],
    history: Annotated[RunHistory, Depends(history_usecase)],
) -> ExtractResponse:
    card = CardInput(
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        seller_params=tuple(SellerParam(p.name, p.value, p.unit) for p in body.seller_params),
    )
    identifier = await history.begin(ReviewCard(card, body.engine))
    try:
        response = await _extract(card, body.engine, usecase, flow)
    except BaseException:
        await history.finish(identifier, None)
        raise
    await history.finish(identifier, response.model_dump_json())
    return response


async def _extract(
    card: CardInput,
    engine: str,
    usecase: ExtractCard,
    flow: StandAttributeFlow | None,
) -> ExtractResponse:
    if engine == "hybrid":
        if flow is None:
            raise ModelFailure("Hybrid attribute flow is not enabled")
        return flow_response(await flow.execute(card))
    result = await usecase.execute(card)
    return ExtractResponse(
        text=result.text,
        threshold=result.threshold,
        missing=list(result.missing),
        values=[
            ExtractedValueSchema(
                attribute=v.attribute,
                value=v.value,
                confidence=None if v.source == "review" else v.confidence,
                source=v.source,
                sources=list(v.sources),
                evidence=v.evidence,
                start=v.start,
                end=v.end,
                status="review" if v.in_review else "accepted",
                review_id=v.review_id,
                acceptance="manual"
                if v.source == "review"
                else "review"
                if v.in_review
                else "automatic",
            )
            for v in result.values
        ],
    )
