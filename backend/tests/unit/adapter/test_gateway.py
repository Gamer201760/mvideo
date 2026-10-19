import asyncio
import json
from typing import Any

import httpx
import pytest

from app.adapter.llm.gateway import GatewayModel
from app.domain.errors import (
    InvalidModelOutput,
    ModelFailure,
    ModelRateLimited,
    ModelTimeout,
    ModelUnavailable,
)
from app.domain.inference import StructuredRequest

REQUEST = StructuredRequest("Extract grounded values", "Card text", {"type": "object"})


def payload(content: str = '{"c":[]}', **overrides: Any) -> dict[str, Any]:
    return {
        "model": "default",
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        **overrides,
    }


def test_wire_contract_uses_default_and_only_supported_fields() -> None:
    async def run() -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://gateway.example/v1/chat/completions"
            assert request.headers["authorization"] == "Bearer fixture-key"
            body = json.loads(request.content)
            assert set(body) == {"model", "messages", "response_format"}
            assert body["model"] == "default"
            assert body["messages"] == [
                {"role": "system", "content": REQUEST.system},
                {"role": "user", "content": REQUEST.prompt},
            ]
            schema = body["response_format"]["json_schema"]
            assert schema["strict"] is True
            assert schema["schema"] == REQUEST.schema
            return httpx.Response(200, json=payload())

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            "fixture-key",
            transport=httpx.MockTransport(respond),
        )
        try:
            result = await model.complete(REQUEST)
            assert result.output == {"c": []}
            assert result.usage.model == "default"
            assert result.usage.input_tokens == 12
            assert result.usage.output_tokens == 4
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_upstream_error_body_is_not_exposed(status: int) -> None:
    async def run() -> None:
        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, text="private upstream details and credentials")
            ),
        )
        try:
            with pytest.raises(ModelFailure) as error:
                await model.complete(REQUEST)
            assert str(status) in str(error.value)
            assert "private" not in str(error.value)
            assert "credentials" not in str(error.value)
            assert isinstance(error.value, ModelRateLimited if status == 429 else ModelUnavailable)
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "body",
    [
        [],
        {},
        {"choices": []},
        {"choices": None},
        payload("not-json"),
        payload("[]"),
        payload(choices=[{"finish_reason": "length", "message": {"content": "{}"}}]),
        payload(choices=[{"finish_reason": "stop", "message": {"content": None}}]),
    ],
)
def test_malformed_or_truncated_output_is_rejected(body: Any) -> None:
    async def run() -> None:
        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
        )
        try:
            with pytest.raises(InvalidModelOutput):
                await model.complete(REQUEST)
        finally:
            await model.aclose()

    asyncio.run(run())


def test_timeout_becomes_safe_model_failure() -> None:
    async def run() -> None:
        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("private request details", request=request)

        model = GatewayModel(
            "https://gateway.example/v1", "default", transport=httpx.MockTransport(timeout)
        )
        try:
            with pytest.raises(ModelTimeout) as error:
                await model.complete(REQUEST)
            assert "private" not in str(error.value)
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure", [httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError]
)
def test_transport_failure_types_are_preserved_without_exposing_request_details(
    failure: type[httpx.RequestError],
) -> None:
    async def run() -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            raise failure("private request details", request=request)

        model = GatewayModel(
            "https://gateway.example/v1", "default", transport=httpx.MockTransport(respond)
        )
        try:
            expected = (
                InvalidModelOutput if failure is httpx.RemoteProtocolError else ModelUnavailable
            )
            with pytest.raises(expected) as error:
                await model.complete(REQUEST)
            assert "private" not in str(error.value)
            assert "gateway.example" not in str(error.value)
        finally:
            await model.aclose()

    asyncio.run(run())
