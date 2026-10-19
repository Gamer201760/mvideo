import time
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request

from app.controller.errors import ErrorResponse
from app.controller.stand.batch_schemas import (
    BatchExtractRequest,
    BatchExtractResponse,
    BatchItemResponse,
    BatchSummary,
)
from app.controller.stand.dependencies import ERRORS, history_usecase
from app.controller.stand.flow_response import flow_response
from app.controller.stand.router import flow_usecase
from app.domain.card_text import SellerParam
from app.domain.errors import ModelFailure
from app.usecase.batch_extraction import BatchExtraction
from app.usecase.review_card import ReviewCard
from app.usecase.run_history import RunHistory
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput

router = APIRouter(tags=["stand"])


@router.post("/extract/batch", response_model=BatchExtractResponse, responses=ERRORS)
async def extract_batch(
    body: BatchExtractRequest,
    request: Request,
    flow: Annotated[StandAttributeFlow | None, Depends(flow_usecase)],
    history: Annotated[RunHistory, Depends(history_usecase)],
) -> BatchExtractResponse:
    if flow is None:
        raise ModelFailure("Hybrid attribute flow is not enabled")
    started = time.perf_counter()
    cards = [
        CardInput(
            title=item.title,
            description=item.description,
            category_id=item.category_id,
            seller_params=tuple(SellerParam(p.name, p.value, p.unit) for p in item.seller_params),
        )
        for item in body.items
    ]
    identifiers: list[str] = []
    finished: set[str] = set()
    items = []
    try:
        for card in cards:
            identifiers.append(await history.begin(ReviewCard(card, "hybrid")))
        batch = await BatchExtraction(flow).execute(cards)
        for item in batch.items:
            response = flow_response(item.result) if item.result is not None else None
            error = (
                ErrorResponse(code=item.error.code, message=type(item.error).message)
                if item.error is not None
                else None
            )
            identifier = identifiers[item.index]
            await history.finish(identifier, response.model_dump_json() if response else None)
            finished.add(identifier)
            items.append(
                BatchItemResponse(
                    id=body.items[item.index].id,
                    run_id=identifier,
                    status="completed" if response is not None else "failed",
                    result=response,
                    error=error,
                )
            )
    finally:
        for identifier in identifiers:
            if identifier not in finished:
                await history.finish(identifier, None)
    calls = [call for call in batch.calls if call.dispatched]
    provider_cards = {index for call in calls for index in call.sku_ids}
    succeeded = sum(item.status == "completed" for item in items)
    input_usage = [call.usage.input_tokens if call.usage else None for call in calls]
    output_usage = [call.usage.output_tokens if call.usage else None for call in calls]
    return BatchExtractResponse(
        items=items,
        summary=BatchSummary(
            requested=len(cards),
            succeeded=succeeded,
            failed=len(cards) - succeeded,
            provider_requests=len(calls),
            provider_cards=len(provider_cards),
            rules_only_cards=sum(
                item.result is not None and item.index not in provider_cards for item in batch.items
            ),
            input_tokens=sum(v for v in input_usage if v is not None)
            if all(v is not None for v in input_usage)
            else None,
            output_tokens=sum(v for v in output_usage if v is not None)
            if all(v is not None for v in output_usage)
            else None,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            provider=cast(Literal["gateway", "local_rules"], request.app.state.runtime["mode"]),
        ),
    )
