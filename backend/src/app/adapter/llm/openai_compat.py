import json
import time
from collections.abc import Mapping
from typing import Any

import httpx

from app.adapter.cache.sqlite_cache import SqliteCache
from app.domain.errors import ModelFailure
from app.domain.inference import Completion, StructuredRequest, Tier, Usage

MAX_TOKENS = 400


class OpenAICompatModel:
    def __init__(self, base_url: str, api_key: str, models: Mapping[Tier, str],
                 cache: SqliteCache | None = None, timeout_s: float = 60.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/", timeout=timeout_s, transport=transport,
            headers={"Authorization": f"Bearer {api_key}"})
        self._models = dict(models)
        self._cache = cache
        self._spent = 0.0
        self.calls = 0

    def spent_rub(self) -> float:
        return round(self._spent, 6)

    def paid_calls(self) -> int:
        return self.calls

    async def complete(self, request: StructuredRequest) -> Completion:
        model = self._models[request.tier]
        schema = json.dumps(request.schema, sort_keys=True)
        key = SqliteCache.key("chat", model, request.system, request.prompt, schema)
        cached = self._cache.get_many([key]).get(key) if self._cache else None
        if cached is not None:
            return Completion(json.loads(cached), Usage(model=model, cost_rub=0.0))
        started = time.monotonic()
        body = await self._post(request, model)
        try:
            content = body["choices"][0]["message"]["content"]
            output = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelFailure(f"Language model returned no JSON: {type(exc).__name__}") from exc
        if not isinstance(output, dict):
            raise ModelFailure("Language model returned JSON that is not an object")
        usage = body.get("usage") or {}
        cost = float(usage.get("cost_rub") or 0.0)
        self._spent += cost
        self.calls += 1
        if self._cache:
            self._cache.put_many({key: json.dumps(output, ensure_ascii=False).encode("utf-8")})
        return Completion(output, Usage(
            model=model, duration_ms=int((time.monotonic() - started) * 1000),
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            cost_rub=cost))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, request: StructuredRequest, model: str) -> dict[str, Any]:
        payload = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "system", "content": request.system},
                         {"role": "user", "content": request.prompt}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "answer", "strict": True, "schema": request.schema}},
        }
        try:
            response = await self._client.post("chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelFailure(f"Language model request failed: {type(exc).__name__}") from exc
        if not isinstance(body, dict):
            raise ModelFailure("Language model response is not an object")
        result: dict[str, Any] = body
        return result
