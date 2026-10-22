from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.controller.errors import ErrorResponse
from app.usecase.readiness import Readiness

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


@router.get("/ready", response_model=ReadinessResponse, responses={503: {"model": ErrorResponse}})
async def ready(request: Request) -> ReadinessResponse:
    readiness: Readiness = request.app.state.readiness
    await readiness.check()
    runtime = {
        **request.app.state.runtime,
        "categories": len(request.app.state.stand.catalog.info().categories),
    }
    return ReadinessResponse(**runtime)
