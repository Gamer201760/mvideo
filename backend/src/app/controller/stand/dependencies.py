from fastapi import Request

from app.controller.errors import ErrorResponse
from app.usecase.review_queue import ReviewQueue
from app.usecase.run_history import RunHistory

ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
}


def review_usecase(request: Request) -> ReviewQueue:
    usecase: ReviewQueue = request.app.state.stand.review
    return usecase


def history_usecase(request: Request) -> RunHistory:
    history: RunHistory = request.app.state.stand.history
    return history
