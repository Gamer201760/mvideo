import json
from pathlib import Path

import httpx
import pytest

from app.adapter.cache.sqlite_cache import SqliteCache
from app.adapter.llm.openai_compat import OpenAICompatModel
from app.domain.errors import ModelFailure
from app.domain.inference import StructuredRequest, Tier

REQUEST = StructuredRequest(system="Найди название", prompt="Утюг Philips GC1740",
                            schema={"type": "object"})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 8, "cost_rub": 0.01}})


@pytest.mark.anyio
async def test_structured_answer_is_parsed_cached_and_priced(tmp_path: Path) -> None:
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return reply('{"title": "Утюг Philips GC1740"}')

    model = OpenAICompatModel("https://polza.test/api/v1", "key",
                              {Tier.FAST: "haiku", Tier.SMART: "sonnet"},
                              SqliteCache(tmp_path / "cache.sqlite"),
                              transport=httpx.MockTransport(handler))
    first = await model.complete(REQUEST)
    second = await model.complete(REQUEST)
    await model.aclose()

    assert first.output == second.output == {"title": "Утюг Philips GC1740"}
    assert first.usage.input_tokens == 40
    assert first.usage.cost_rub == 0.01
    assert len(sent) == 1
    assert sent[0]["model"] == "haiku"
    assert model.spent_rub() == 0.01


@pytest.mark.anyio
async def test_answer_that_is_not_json_is_a_model_failure() -> None:
    model = OpenAICompatModel("https://polza.test/api/v1", "key",
                              {Tier.FAST: "haiku", Tier.SMART: "sonnet"},
                              transport=httpx.MockTransport(lambda _: reply("Утюг Philips")))

    with pytest.raises(ModelFailure):
        await model.complete(REQUEST)
    await model.aclose()
