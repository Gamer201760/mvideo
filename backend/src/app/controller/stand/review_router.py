from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.controller.stand.dependencies import ERRORS, review_usecase
from app.controller.stand.schemas import (
    AddReviewRequest,
    CardReviewResponse,
    ExtractRequest,
    ResolveRequest,
    ReviewItemSchema,
    ReviewListResponse,
    SellerParamSchema,
)
from app.domain.card_text import SellerParam
from app.domain.review import ReviewItem, ReviewStatus
from app.usecase.review_query import ReviewQuery
from app.usecase.review_queue import ReviewQueue
from app.usecase.stand_ports import CardInput

router = APIRouter(tags=["stand"])


@router.get("/review", response_model=ReviewListResponse, responses=ERRORS)
async def review_list(
    usecase: Annotated[ReviewQueue, Depends(review_usecase)],
    status: Annotated[ReviewStatus | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    exclude_card_key: Annotated[str | None, Query(max_length=32)] = None,
) -> ReviewListResponse:
    page = await usecase.page(
        ReviewQuery(
            status=status,
            offset=offset,
            limit=limit,
            exclude_card_key=exclude_card_key,
        )
    )
    return ReviewListResponse(items=[_item(i) for i in page.items], total=page.total)


@router.post("/review/card", response_model=CardReviewResponse, responses=ERRORS)
async def card_reviews(
    body: ExtractRequest,
    usecase: Annotated[ReviewQueue, Depends(review_usecase)],
) -> CardReviewResponse:
    state = await usecase.for_card(
        CardInput(
            title=body.title,
            description=body.description,
            category_id=body.category_id,
            seller_params=tuple(SellerParam(p.name, p.value, p.unit) for p in body.seller_params),
        )
    )
    return CardReviewResponse(card_key=state.card_key, items=[_item(i) for i in state.items])


@router.post("/review/add", response_model=ReviewItemSchema, responses=ERRORS)
async def review_add(
    body: AddReviewRequest, usecase: Annotated[ReviewQueue, Depends(review_usecase)]
) -> ReviewItemSchema:
    card = body.card
    return _item(
        await usecase.add(
            CardInput(
                title=card.title,
                description=card.description,
                category_id=card.category_id,
                seller_params=tuple(
                    SellerParam(p.name, p.value, p.unit) for p in card.seller_params
                ),
            ),
            body.attribute,
            body.value,
            body.evidence,
        )
    )


@router.post("/review/{item_id}", response_model=ReviewItemSchema, responses=ERRORS)
async def review_resolve(
    item_id: str, body: ResolveRequest, usecase: Annotated[ReviewQueue, Depends(review_usecase)]
) -> ReviewItemSchema:
    return _item(
        await usecase.resolve(
            item_id,
            body.action,
            body.value,
            override=body.override,
            expected_value=body.expected_value,
        )
    )


@router.get("/review/{item_id}/card", response_model=ExtractRequest, responses=ERRORS)
async def review_card(
    item_id: str, usecase: Annotated[ReviewQueue, Depends(review_usecase)]
) -> ExtractRequest:
    saved = await usecase.card(item_id)
    card = saved.input
    return ExtractRequest(
        engine=saved.engine,
        title=card.title,
        description=card.description,
        category_id=card.category_id,
        seller_params=[
            SellerParamSchema(name=p.name, value=p.value, unit=p.unit) for p in card.seller_params
        ],
    )


def _item(item: ReviewItem) -> ReviewItemSchema:
    return ReviewItemSchema(
        id=item.id,
        category_id=item.category_id,
        title=item.title,
        attribute=item.attribute,
        value=item.value,
        confidence=item.confidence,
        source=item.source,
        evidence=item.evidence,
        status=item.status,
        resolved_value=item.resolved_value,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )
