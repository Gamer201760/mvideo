import asyncio
import hashlib
import logging
import threading

import httpx
import pytest
from tests.unit.adapter.test_gateway import REQUEST, payload

from app.adapter.llm.gateway import GatewayModel
from app.adapter.llm.gateway_retry import GatewayRetry
from app.adapter.log.stdlib import StdlibLogger
from app.domain.errors import InvalidModelOutput


def test_retry_diagnostics_contain_only_safe_structured_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="test.gateway")

    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return (
                httpx.Response(429, text="private-upstream-response")
                if calls == 1
                else httpx.Response(200, json=payload())
            )

        model = GatewayModel(
            "https://private-user:private-password@gateway.example/v1",
            "default",
            "private-key",
            logger=StdlibLogger("test.gateway"),
            retry=GatewayRetry(base_delay_s=0),
            transport=httpx.MockTransport(respond),
        )
        try:
            assert (await model.complete(REQUEST)).usage.attempts == 2
        finally:
            await model.aclose()

    asyncio.run(run())
    events = [record.getMessage() for record in caplog.records]
    assert len(events) == 5
    attempts = [event for event in events if event.startswith("gateway_attempt ")]
    assert len(attempts) == 2
    assert len([event for event in events if event.startswith("gateway_response ")]) == 2
    text = " ".join(events)
    assert not any(
        secret in text
        for secret in (
            "private-",
            "Card text",
            "Extract grounded",
            "gateway.example",
            '"c":',
        )
    )
    assert "status=429" in attempts[0] and "attempt=1" in attempts[0]
    assert "status=200" in attempts[1] and "attempt=2" in attempts[1]
    assert "response_bytes=25" in events[0]
    assert hashlib.sha256(b"private-upstream-response").hexdigest() in events[0]
    request_ids = [event.split("request_id=")[1].split()[0] for event in events]
    assert len(set(request_ids)) == 1


def test_schema_validation_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    validation_threads: list[int] = []

    def validate(output: object, schema: object) -> None:
        validation_threads.append(threading.get_ident())

    monkeypatch.setattr("app.adapter.llm.gateway.validate_output", validate)

    async def run() -> None:
        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload())),
        )
        try:
            await model.complete(REQUEST)
            assert validation_threads and validation_threads[0] != threading.get_ident()
        finally:
            await model.aclose()

    asyncio.run(run())


def test_response_is_recorded_before_schema_validation_fails(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO, logger="test.gateway.before-parse")

    def reject(output: object, schema: object) -> None:
        events = [record.getMessage() for record in caplog.records]
        assert len(events) == 1 and events[0].startswith("gateway_response ")
        assert "response_sha256=" in events[0] and "response_bytes=" in events[0]
        raise InvalidModelOutput()

    monkeypatch.setattr("app.adapter.llm.gateway.validate_output", reject)

    async def run() -> None:
        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            logger=StdlibLogger("test.gateway.before-parse"),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload())),
        )
        try:
            with pytest.raises(InvalidModelOutput):
                await model.complete(REQUEST)
        finally:
            await model.aclose()

    asyncio.run(run())
    assert "error='invalid_model_output'" in caplog.records[-1].getMessage()
