import asyncio
import math
import time
from collections.abc import Mapping
from typing import Any

import httpx

from app.domain.decision import (
    Answer,
    BinaryAnswer,
    BinaryQuestion,
    ChoiceAnswer,
    ChoiceQuestion,
    Decision,
    DecisionRequest,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)
from app.domain.errors import DecisionFailure
from app.domain.inference import Tier, Usage

TYPESAFE_URL = "https://api.typesafe.ai"
ENDPOINT = "/v1/systemone"
DEFAULT_MODEL_NAME = "jev-latest"
DEFAULT_MODELS = {Tier.FAST: DEFAULT_MODEL_NAME, Tier.SMART: DEFAULT_MODEL_NAME}
ERROR_BODY_LIMIT = 300
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 529})
RETRY_BASE_S = 1.0


class SystemOneModel:
    def __init__(
        self,
        base_url: str = TYPESAFE_URL,
        api_key: str | None = None,
        models: Mapping[Tier, str] = DEFAULT_MODELS,
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        retries: int = 0,
        retry_base_s: float = RETRY_BASE_S,
    ) -> None:
        self._models = dict(models)
        self._retries = retries
        self._retry_base_s = retry_base_s
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=timeout_s, transport=transport
        )

    async def decide(self, request: DecisionRequest) -> Decision:
        model = self._models[request.tier]
        body = {
            "model": model,
            "state": request.state,
            "questions": {key: _question(q) for key, q in request.questions.items()},
        }
        started = time.perf_counter()
        response = await self._post(body)
        duration_ms = round((time.perf_counter() - started) * 1000)
        if response.is_error:
            raise DecisionFailure(
                f"Decision model failed: HTTP {response.status_code} "
                f"{response.text[:ERROR_BODY_LIMIT]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DecisionFailure(f"Decision model failed: {exc}") from exc
        answers = _field(payload, "answers", dict)
        return Decision(
            answers={
                key: _answer(key, question, answers.get(key))
                for key, question in request.questions.items()
            },
            usage=_usage(payload, model, duration_ms),
        )

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._client.post(ENDPOINT, json=body)
            except httpx.HTTPError as exc:
                if attempt >= self._retries:
                    raise DecisionFailure(f"Decision model failed: {exc!r}") from exc
            else:
                if response.status_code not in RETRY_STATUSES or attempt >= self._retries:
                    return response
            await asyncio.sleep(self._retry_base_s * 2**attempt)
            attempt += 1

    async def aclose(self) -> None:
        await self._client.aclose()


def _question(question: Question) -> dict[str, Any]:
    match question:
        case ChoiceQuestion(instructions, options):
            return {"type": "choice", "instructions": instructions, "criteria": dict(options)}
        case ScoreQuestion(instructions, levels):
            return {"type": "score", "instructions": instructions, "criteria": list(levels)}
        case BinaryQuestion(instructions):
            return {"type": "noul", "instructions": instructions}


def _answer(key: str, question: Question, raw: object) -> Answer:
    if not isinstance(raw, dict):
        raise DecisionFailure(f"Decision model failed: no answer for {key!r}")
    match question:
        case ChoiceQuestion(_, options):
            choice = _field(raw, "choice", str)
            if choice not in options:
                raise DecisionFailure(f"Decision model failed: unknown option {choice!r}")
            probabilities = _probabilities(raw, list(options))
            return ChoiceAnswer(
                choice=choice,
                confidence=_probability(raw, "confidence"),
                probabilities=probabilities,
            )
        case ScoreQuestion(_, levels):
            score = _number(raw, "score")
            if not 0 <= score <= len(levels) - 1:
                raise DecisionFailure(f"Decision model failed: score {score} out of range")
            by_level = _probabilities(raw, [str(level) for level in range(len(levels))])
            return ScoreAnswer(
                score=score,
                confidence=_probability(raw, "confidence"),
                probabilities=tuple(by_level.values()),
            )
        case BinaryQuestion():
            return BinaryAnswer(probability=_probability(raw, "noul"))


def _probabilities(raw: dict[str, Any], keys: list[str]) -> dict[str, float]:
    values = _field(raw, "probabilities", dict)
    if set(values) != set(keys):
        raise DecisionFailure("Decision model failed: probabilities do not match criteria")
    return {key: _probability(values, key) for key in keys}


def _probability(raw: dict[str, Any], key: str) -> float:
    value = _number(raw, key)
    if not 0 <= value <= 1:
        raise DecisionFailure(f"Decision model failed: {key} {value} is not a probability")
    return value


def _number(raw: dict[str, Any], key: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise DecisionFailure(f"Decision model failed: {key!r} is not a number")
    return float(value)


def _field[T](raw: object, key: str, kind: type[T]) -> T:
    value = raw.get(key) if isinstance(raw, dict) else None
    if not isinstance(value, kind):
        raise DecisionFailure(f"Decision model failed: {key!r} is missing or malformed")
    return value


def _usage(payload: dict[str, Any], model: str, duration_ms: int) -> Usage:
    usage = payload.get("usage")
    tokens = usage if isinstance(usage, dict) else {}
    reported = payload.get("model")
    return Usage(
        model=reported if isinstance(reported, str) else model,
        duration_ms=duration_ms,
        input_tokens=_count(tokens.get("input_tokens")),
        output_tokens=_count(tokens.get("output_tokens")),
        cost_usd=_cost(tokens.get("cost")),
    )


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _cost(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value) if value >= 0 else None
