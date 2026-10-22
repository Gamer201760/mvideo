import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from tests.unit.adapter.test_gateway import REQUEST, payload

from app.adapter.llm.gateway import GatewayModel
from app.adapter.llm.gateway_retry import GatewayRetry
from app.domain.errors import InvalidModelOutput, ModelFailure, ModelRateLimited, ModelUnavailable

FAST_RETRY = GatewayRetry(base_delay_s=0, max_delay_s=0)


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_transient_status_retries_once_then_returns_real_output(status: int) -> None:
    async def run() -> None:
        requests: list[bytes] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request.content)
            return (
                httpx.Response(status, text="private")
                if len(requests) == 1
                else httpx.Response(200, json=payload())
            )

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=FAST_RETRY,
            transport=httpx.MockTransport(respond),
        )
        try:
            result = await model.complete(REQUEST)
            assert result.output == {"c": []}
            assert result.usage.attempts == len(requests) == 2
            assert requests[0] == requests[1]
            assert result.usage.input_tokens is result.usage.output_tokens is None
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ConnectTimeout])
def test_connection_failure_before_response_can_retry(failure: type[httpx.RequestError]) -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise failure("private connection details", request=request)
            return httpx.Response(200, json=payload())

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=FAST_RETRY,
            transport=httpx.MockTransport(respond),
        )
        try:
            result = await model.complete(REQUEST)
            assert result.usage.attempts == calls == 2
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_exhaustion_is_typed_failure_after_two_actual_attempts(status: int) -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(status, text="private response")

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=FAST_RETRY,
            transport=httpx.MockTransport(respond),
        )
        try:
            with pytest.raises(ModelRateLimited if status == 429 else ModelUnavailable) as error:
                await model.complete(REQUEST)
            assert error.value.attempts == calls == 2
            assert "private" not in str(error.value)
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 409, 422, 500])
def test_other_http_failures_are_not_retried(status: int) -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(status, text="private response")

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=FAST_RETRY,
            transport=httpx.MockTransport(respond),
        )
        try:
            with pytest.raises(ModelUnavailable) as error:
                await model.complete(REQUEST)
            assert error.value.attempts == calls == 1
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.ReadError,
        httpx.WriteError,
        httpx.RemoteProtocolError,
        httpx.DecodingError,
    ],
)
def test_ambiguous_transport_failures_are_not_retried(failure: type[httpx.RequestError]) -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise failure("private transport details", request=request)

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=FAST_RETRY,
            transport=httpx.MockTransport(respond),
        )
        try:
            with pytest.raises(ModelFailure) as error:
                await model.complete(REQUEST)
            assert error.value.attempts == calls == 1
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("content", ['{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', "not JSON"])
def test_invalid_json_is_not_retried(content: str) -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=payload(content))

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=FAST_RETRY,
            transport=httpx.MockTransport(respond),
        )
        try:
            with pytest.raises(InvalidModelOutput) as error:
                await model.complete(REQUEST)
            assert error.value.attempts == calls == 1
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "header,expected",
    [("0.5", 0.5), ("999", 2), ("-1", 0), ("bad", 0.25), ("NaN", 0.25), ("inf", 0.25)],
)
def test_retry_after_is_honored_and_capped(header: str, expected: float) -> None:
    assert GatewayRetry().delay(1, header) == expected


def test_retry_after_http_date_and_exponential_backoff() -> None:
    policy = GatewayRetry(max_attempts=4)
    future = format_datetime(datetime.now(UTC) + timedelta(hours=1))
    past = format_datetime(datetime.now(UTC) - timedelta(hours=1))
    assert policy.delay(1, future) == 2
    assert policy.delay(1, past) == 0
    assert [policy.delay(n, None) for n in range(1, 4)] == [0.25, 0.5, 1]


@pytest.mark.parametrize("maximum", [0, 5])
def test_attempt_budget_is_bounded(maximum: int) -> None:
    with pytest.raises(ValueError):
        GatewayRetry(max_attempts=maximum)


def test_retry_engine_schedules_the_capped_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def wait(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.adapter.llm.gateway.asyncio.sleep", wait)

    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return (
                httpx.Response(429, headers={"retry-after": "999"})
                if calls == 1
                else httpx.Response(200, json=payload())
            )

        model = GatewayModel(
            "https://gateway.example/v1", "default", transport=httpx.MockTransport(respond)
        )
        try:
            assert (await model.complete(REQUEST)).usage.attempts == calls == 2
            assert delays == [2]
        finally:
            await model.aclose()

    asyncio.run(run())
