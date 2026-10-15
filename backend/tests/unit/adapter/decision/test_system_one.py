import json
from typing import Any

import httpx
import pytest

from app.adapter.decision.system_one import SystemOneModel
from app.domain.decision import (
    BinaryAnswer,
    BinaryQuestion,
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionRequest,
    ScoreAnswer,
    ScoreQuestion,
)
from app.domain.errors import DecisionFailure
from app.domain.inference import Tier

REQUEST = DecisionRequest(
    state={"subject": "Charged twice", "body": "Please refund ASAP"},
    questions={
        "department": ChoiceQuestion(
            "Which department should handle this?",
            {"billing": "invoices, refunds", "technical": "bugs, outages"},
        ),
        "urgency": ScoreQuestion("How urgent is it?", ["low", "medium", "high"]),
        "refund": BinaryQuestion("Does the customer ask for a refund?"),
    },
    tier=Tier.SMART,
)
ANSWERS = {
    "department": {
        "type": "choice",
        "choice": "billing",
        "confidence": 0.9,
        "probabilities": {"billing": 0.95, "technical": 0.05},
    },
    "urgency": {
        "type": "score",
        "score": 1.43,
        "confidence": 0.6,
        "legend": {"0": "low", "1": "medium", "2": "high"},
        "probabilities": {"0": 0.0, "1": 0.57, "2": 0.43},
    },
    "refund": {"type": "noul", "noul": 0.88},
}
PAYLOAD = {
    "model": "jev-1.13.0",
    "answers": ANSWERS,
    "usage": {"input_tokens": 120, "output_tokens": 3},
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def model_returning(
    response: httpx.Response | Exception, seen: list[httpx.Request] | None = None
) -> SystemOneModel:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    return SystemOneModel(
        base_url="http://decider.test",
        api_key="secret",
        models={Tier.FAST: "jev-fast", Tier.SMART: "jev-latest"},
        transport=httpx.MockTransport(handle),
    )


def with_answer(key: str, **changes: Any) -> dict[str, Any]:
    return PAYLOAD | {"answers": ANSWERS | {key: ANSWERS[key] | changes}}


@pytest.mark.anyio
async def test_sends_system_one_request_and_maps_answers() -> None:
    seen: list[httpx.Request] = []
    model = model_returning(httpx.Response(200, json=PAYLOAD), seen)

    decision = await model.decide(REQUEST)
    await model.aclose()

    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == "http://decider.test/v1/systemone"
    assert request.headers["Authorization"] == "Bearer secret"
    assert json.loads(request.content) == {
        "model": "jev-latest",
        "state": {"subject": "Charged twice", "body": "Please refund ASAP"},
        "questions": {
            "department": {
                "type": "choice",
                "instructions": "Which department should handle this?",
                "criteria": {"billing": "invoices, refunds", "technical": "bugs, outages"},
            },
            "urgency": {
                "type": "score",
                "instructions": "How urgent is it?",
                "criteria": ["low", "medium", "high"],
            },
            "refund": {"type": "noul", "instructions": "Does the customer ask for a refund?"},
        },
    }
    assert decision.answers == {
        "department": ChoiceAnswer(
            choice="billing", confidence=0.9, probabilities={"billing": 0.95, "technical": 0.05}
        ),
        "urgency": ScoreAnswer(score=1.43, confidence=0.6, probabilities=(0.0, 0.57, 0.43)),
        "refund": BinaryAnswer(probability=0.88),
    }
    assert decision.usage.model == "jev-1.13.0"
    assert decision.usage.input_tokens == 120
    assert decision.usage.output_tokens == 3
    assert decision.usage.cost_usd is None


@pytest.mark.anyio
async def test_local_server_without_key_or_usage() -> None:
    seen: list[httpx.Request] = []
    payload = {"answers": ANSWERS}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    model = SystemOneModel(base_url="http://laya:8000", transport=httpx.MockTransport(handle))

    decision = await model.decide(REQUEST)

    assert "Authorization" not in seen[0].headers
    assert decision.usage.model == "jev-latest"
    assert decision.usage.input_tokens is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "outcome",
    [
        httpx.Response(401, json={"detail": "invalid key"}),
        httpx.Response(422, json={"detail": "criteria missing"}),
        httpx.Response(529, text="overloaded"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=["not", "object"]),
        httpx.Response(200, json={"model": "jev"}),
        httpx.Response(200, json=PAYLOAD | {"answers": {"department": ANSWERS["department"]}}),
        httpx.Response(200, json=with_answer("department", choice="legal")),
        httpx.Response(200, json=with_answer("department", probabilities={"billing": 1.0})),
        httpx.Response(200, json=with_answer("department", confidence=1.5)),
        httpx.Response(200, json=with_answer("urgency", score=2.5)),
        httpx.Response(200, json=with_answer("urgency", probabilities=[0.0, 0.57, 0.43])),
        httpx.Response(200, json=with_answer("refund", noul="yes")),
        httpx.Response(200, json=with_answer("refund", noul=True)),
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
    ],
    ids=[
        "unauthorized",
        "invalid-request",
        "overloaded",
        "not-json",
        "not-object",
        "no-answers",
        "missing-answer",
        "unknown-option",
        "partial-probabilities",
        "confidence-out-of-range",
        "score-out-of-range",
        "score-probabilities-list",
        "binary-not-number",
        "binary-bool",
        "connect-error",
        "timeout",
    ],
)
async def test_failures_become_decision_failure(outcome: httpx.Response | Exception) -> None:
    model = model_returning(outcome)

    with pytest.raises(DecisionFailure):
        await model.decide(REQUEST)


@pytest.mark.anyio
async def test_reads_reported_cost_and_configured_model_name() -> None:
    seen: list[httpx.Request] = []
    payload = PAYLOAD | {"model": "typesafe/jev-1.13-20260917",
                         "usage": {"input_tokens": 598, "output_tokens": 154, "cost": 0.000025}}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    name = "typesafe/jev-1.13"
    model = SystemOneModel(base_url="https://openrouter.test/api",
                           models={Tier.FAST: name, Tier.SMART: name},
                           transport=httpx.MockTransport(handle))

    decision = await model.decide(REQUEST)

    assert json.loads(seen[0].content)["model"] == name
    assert str(seen[0].url) == "https://openrouter.test/api/v1/systemone"
    assert decision.usage.cost_usd == 0.000025
    assert decision.usage.model == "typesafe/jev-1.13-20260917"


@pytest.mark.anyio
async def test_retries_rate_limits_then_succeeds() -> None:
    replies = [httpx.Response(429, text="slow down"), httpx.Response(200, json=PAYLOAD)]

    def handle(request: httpx.Request) -> httpx.Response:
        return replies.pop(0)

    model = SystemOneModel(base_url="http://decider.test", transport=httpx.MockTransport(handle),
                           retries=2, retry_base_s=0.0)

    decision = await model.decide(REQUEST)

    assert replies == []
    assert decision.usage.input_tokens == 120


@pytest.mark.anyio
async def test_gives_up_after_retries() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(529, text="overloaded")

    model = SystemOneModel(base_url="http://decider.test", transport=httpx.MockTransport(handle),
                           retries=1, retry_base_s=0.0)

    with pytest.raises(DecisionFailure, match="529"):
        await model.decide(REQUEST)
