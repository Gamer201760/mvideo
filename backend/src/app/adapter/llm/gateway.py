import json
import time
from typing import Any

import httpx

from app.domain.errors import InvalidModelOutput, ModelRateLimited, ModelTimeout, ModelUnavailable
from app.domain.inference import Completion, StructuredRequest, Usage


class GatewayModel:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url or not model or timeout_s <= 0:
            raise ValueError("Model URL, name and positive request limits are required")
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout_s,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def complete(self, request: StructuredRequest) -> Completion:
        started = time.perf_counter()
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
            response = await self._client.post("chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise ModelTimeout() from exc
        except (httpx.RemoteProtocolError, httpx.DecodingError) as exc:
            raise InvalidModelOutput() from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailable() from exc
        if response.status_code == 429:
            raise ModelRateLimited("Model returned HTTP 429")
        if not response.is_success:
            raise ModelUnavailable(f"Model returned HTTP {response.status_code}")
        try:
            raw = response.json()
            choice = raw["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise InvalidModelOutput()
            output = json.loads(choice["message"]["content"])
            if not isinstance(output, dict):
                raise InvalidModelOutput()
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            raise InvalidModelOutput() from exc
        usage = raw.get("usage")
        tokens = usage if isinstance(usage, dict) else {}
        reported = raw.get("model")
        return Completion(
            output=output,
            usage=Usage(
                model=reported if isinstance(reported, str) else self._model,
                duration_ms=round((time.perf_counter() - started) * 1000),
                input_tokens=_count(tokens, "prompt_tokens"),
                output_tokens=_count(tokens, "completion_tokens"),
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _count(raw: dict[str, Any], name: str) -> int | None:
    value = raw.get(name)
    return value if type(value) is int and value >= 0 else None
