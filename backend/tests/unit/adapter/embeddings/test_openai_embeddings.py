import json
from pathlib import Path

import httpx
import pytest

from app.adapter.cache.sqlite_cache import SqliteCache
from app.adapter.embeddings.openai_compat import QUERY_INSTRUCTION, OpenAICompatEmbeddings
from app.domain.errors import EmbeddingsFailure


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_vectors_are_cached_and_cost_is_counted(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        data = [{"index": i, "embedding": [float(i), 1.0]} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data, "usage": {"cost_rub": 0.5}})

    model = OpenAICompatEmbeddings("https://polza.test/api/v1", "key", "qwen", 2,
                                   SqliteCache(tmp_path / "cache.sqlite"),
                                   transport=httpx.MockTransport(handler))
    first = await model.embed_documents(["утюг", "фен"])
    again = await model.embed_documents(["фен", "утюг"])
    query = await model.embed_queries(["утюг"])
    await model.aclose()

    assert first == [[0.0, 1.0], [1.0, 1.0]]
    assert again == [[1.0, 1.0], [0.0, 1.0]]
    assert query == [[0.0, 1.0]]
    assert [r["input"] for r in requests] == [["утюг", "фен"], [QUERY_INSTRUCTION + "утюг"]]
    assert requests[0]["dimensions"] == 2
    assert model.spent_rub() == 1.0


@pytest.mark.anyio
async def test_provider_error_becomes_embeddings_failure() -> None:
    model = OpenAICompatEmbeddings(
        "https://polza.test/api/v1", "key", "qwen", 2,
        transport=httpx.MockTransport(lambda _: httpx.Response(402, json={"error": "balance"})))

    with pytest.raises(EmbeddingsFailure):
        await model.embed_documents(["утюг"])
    await model.aclose()
