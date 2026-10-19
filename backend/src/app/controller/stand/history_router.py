from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.controller.stand.dependencies import ERRORS, history_usecase
from app.controller.stand.schemas import (
    ExtractRequest,
    ExtractResponse,
    RunDetailResponse,
    RunListResponse,
    RunSummarySchema,
    SellerParamSchema,
)
from app.usecase.run_history import RunHistory

router = APIRouter(tags=["stand"])


@router.get("/runs", response_model=RunListResponse, responses=ERRORS)
async def history_list(
    history: Annotated[RunHistory, Depends(history_usecase)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RunListResponse:
    items, total = await history.page(offset, limit)
    return RunListResponse(
        total=total,
        items=[
            RunSummarySchema(
                id=run.id,
                title=run.card.input.title,
                engine=run.card.engine,
                status=run.status,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
            for run in items
        ],
    )


@router.get("/runs/{run_id}", response_model=RunDetailResponse, responses=ERRORS)
async def history_detail(
    run_id: str,
    history: Annotated[RunHistory, Depends(history_usecase)],
) -> RunDetailResponse:
    run = await history.get(run_id)
    card = run.card.input
    return RunDetailResponse(
        input=ExtractRequest(
            engine=run.card.engine,
            title=card.title,
            description=card.description,
            category_id=card.category_id,
            seller_params=[
                SellerParamSchema(name=p.name, value=p.value, unit=p.unit)
                for p in card.seller_params
            ],
        ),
        result=ExtractResponse.model_validate_json(run.result_json)
        if run.result_json is not None
        else None,
        status=run.status,
    )
