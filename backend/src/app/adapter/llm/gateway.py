import asyncio
import hashlib
import json
import time
from typing import Any
from uuid import uuid4

import httpx

from app.adapter.llm.gateway_retry import RETRYABLE_STATUSES, GatewayRetry
from app.adapter.llm.output_validation import validate_output
from app.domain.errors import (
    InvalidModelOutput,
    ModelFailure,
    ModelRateLimited,
    ModelTimeout,
    ModelUnavailable,
)
from app.domain.inference import Completion, StructuredRequest, Usage
from app.usecase.interface import Logger


class GatewayModel:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        logger: Logger | None = None,
        retry: GatewayRetry | None = None,
    ) -> None:
        if not base_url or not model or timeout_s <= 0:
            raise ValueError("Model URL, name and positive request limits are required")
        self._model, self._timeout_s = model, timeout_s
        self._logger, self._retry = logger, retry or GatewayRetry()
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout_s,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def complete(self, request: StructuredRequest) -> Completion:
        started, attempt = time.perf_counter(), 0
        request_id = uuid4().hex
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "attribute_selection",
                    "strict": True,
                    "schema": request.schema,
                },
            },
        }
        try:
            async with asyncio.timeout(self._timeout_s):
                for attempt in range(1, self._retry.max_attempts + 1):
                    response = None
                    failure = None
                    retryable = False
                    sent = time.perf_counter()
                    try:
                        response = await self._client.post("chat/completions", json=body)
                        self._received(request_id, attempt, sent, response)
                        if response.status_code == 429:
                            raise ModelRateLimited("Model returned HTTP 429")
                        if not response.is_success:
                            raise ModelUnavailable(f"Model returned HTTP {response.status_code}")
                        completion = await asyncio.to_thread(
                            self._decode, response, request, attempt, started
                        )
                    except httpx.HTTPError as error:
                        failure = _transport_failure(error)
                        retryable = isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout))
                    except ModelFailure as error:
                        failure = error
                        retryable = (
                            response is not None and response.status_code in RETRYABLE_STATUSES
                        )
                    self._diagnose(request_id, attempt, sent, response, failure)
                    if failure is None:
                        return completion
                    failure.attempts = attempt
                    if not retryable or attempt == self._retry.max_attempts:
                        raise failure from None
                    delay = self._retry.delay(
                        attempt, response.headers.get("retry-after") if response else None
                    )
                    if self._logger is not None:
                        self._logger.info(
                            "gateway_retry", request_id=request_id, attempt=attempt, delay_s=delay
                        )
                    await asyncio.sleep(delay)
        except TimeoutError:
            if self._logger is not None:
                self._logger.warning("gateway_timeout", request_id=request_id, attempts=attempt)
            raise ModelTimeout(attempts=attempt) from None
        except asyncio.CancelledError as error:
            error.__dict__["model_attempts"] = attempt
            if self._logger is not None:
                self._logger.info("gateway_cancelled", request_id=request_id, attempts=attempt)
            raise
        raise ModelUnavailable(attempts=attempt)

    def _decode(
        self,
        response: httpx.Response,
        request: StructuredRequest,
        attempt: int,
        started: float,
    ) -> Completion:
        try:
            raw = response.json()
            choice = raw["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise InvalidModelOutput()
            output = json.loads(choice["message"]["content"], parse_constant=_invalid_constant)
            if not isinstance(output, dict):
                raise InvalidModelOutput()
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
            raise InvalidModelOutput() from None
        validate_output(output, request.schema)
        usage = raw.get("usage")
        tokens = usage if isinstance(usage, dict) else {}
        reported = raw.get("model")
        return Completion(
            output=output,
            usage=Usage(
                model=reported if isinstance(reported, str) else self._model,
                duration_ms=round((time.perf_counter() - started) * 1000),
                input_tokens=_count(tokens, "prompt_tokens") if attempt == 1 else None,
                output_tokens=_count(tokens, "completion_tokens") if attempt == 1 else None,
                attempts=attempt,
            ),
        )

    def _received(
        self, request_id: str, attempt: int, started: float, response: httpx.Response
    ) -> None:
        if self._logger is not None:
            self._logger.info(
                "gateway_response",
                request_id=request_id,
                attempt=attempt,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                status=response.status_code,
                response_bytes=len(response.content),
                response_sha256=hashlib.sha256(response.content).hexdigest(),
            )

    def _diagnose(
        self,
        request_id: str,
        attempt: int,
        started: float,
        response: httpx.Response | None,
        failure: ModelFailure | None,
    ) -> None:
        if self._logger is None:
            return
        record = self._logger.warning if failure else self._logger.info
        record(
            "gateway_attempt",
            request_id=request_id,
            attempt=attempt,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            status=response.status_code if response is not None else None,
            response_bytes=len(response.content) if response is not None else 0,
            response_sha256=hashlib.sha256(response.content).hexdigest()
            if response is not None
            else None,
            error=failure.code if failure else None,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _transport_failure(error: httpx.HTTPError) -> ModelFailure:
    if isinstance(error, (httpx.RemoteProtocolError, httpx.DecodingError)):
        return InvalidModelOutput()
    if isinstance(error, httpx.TimeoutException):
        return ModelTimeout()
    return ModelUnavailable()


def _count(raw: dict[str, Any], name: str) -> int | None:
    value = raw.get(name)
    return value if type(value) is int and value >= 0 else None


def _invalid_constant(value: str) -> None:
    raise ValueError("Invalid JSON constant")
