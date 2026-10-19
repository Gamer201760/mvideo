from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    ready: bool
    mode: Literal["gateway", "local_rules"]
    model: str | None
    categories: int
    synthetic: bool


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def ready(request: Request) -> ReadinessResponse:
    runtime = {
        **request.app.state.runtime,
        "categories": len(request.app.state.stand.catalog.info().categories),
    }
    return ReadinessResponse(**runtime)
