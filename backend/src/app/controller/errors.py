from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.domain.errors import DomainError, InvalidQuestion, ModelFailure
from app.domain.review import (
    InvalidCorrection,
    ReviewAlreadyResolved,
    ReviewItemNotFound,
    StandUnavailable,
    UnknownCategory,
)
from app.domain.text_reading import EmptyText, TextIndexMissing
from app.usecase.interface import Logger

STATUS_BY_ERROR: dict[type[DomainError], HTTPStatus] = {
    InvalidQuestion: HTTPStatus.UNPROCESSABLE_ENTITY,
    ModelFailure: HTTPStatus.SERVICE_UNAVAILABLE,
    ReviewItemNotFound: HTTPStatus.NOT_FOUND,
    ReviewAlreadyResolved: HTTPStatus.CONFLICT,
    InvalidCorrection: HTTPStatus.UNPROCESSABLE_ENTITY,
    UnknownCategory: HTTPStatus.UNPROCESSABLE_ENTITY,
    StandUnavailable: HTTPStatus.SERVICE_UNAVAILABLE,
    EmptyText: HTTPStatus.UNPROCESSABLE_ENTITY,
    TextIndexMissing: HTTPStatus.SERVICE_UNAVAILABLE,
}


class ErrorResponse(BaseModel):
    code: str
    message: str


class ErrorHandlers:
    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def register(self, app: FastAPI) -> None:
        app.add_exception_handler(DomainError, self.domain_error)
        app.add_exception_handler(RequestValidationError, self.validation_error)
        app.add_exception_handler(HTTPException, self.http_error)
        app.add_exception_handler(Exception, self.unexpected_error)

    async def domain_error(self, request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        status = next(
            (STATUS_BY_ERROR[kind] for kind in type(exc).__mro__ if kind in STATUS_BY_ERROR), None
        )
        if status is None:
            self._logger.error("unmapped_domain_error", code=exc.code, path=request.url.path)
            return _envelope(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "Internal error")
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            self._logger.warning(
                "domain_failure", code=exc.code, path=request.url.path, detail=exc.message
            )
            return _envelope(status, exc.code, type(exc).message)
        return _envelope(status, exc.code, exc.message)

    async def validation_error(self, request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        message = f"Invalid request: {', '.join(fields)}" if fields else "Invalid request"
        return _envelope(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", message)

    async def http_error(self, request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, HTTPException)
        status = HTTPStatus(exc.status_code)
        code = status.phrase.lower().replace(" ", "_").replace("-", "_")
        return _envelope(status, code, status.phrase)

    async def unexpected_error(self, request: Request, exc: Exception) -> JSONResponse:
        self._logger.error("unexpected_error", exc=exc, path=request.url.path)
        return _envelope(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "Internal error")


def _envelope(status: HTTPStatus | int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(code=code, message=message)
    return JSONResponse(status_code=status, content=body.model_dump())
