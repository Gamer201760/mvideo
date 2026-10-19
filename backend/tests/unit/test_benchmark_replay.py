import asyncio
import json

import pytest
from benchmarks.replay import SavedResponse

from app.domain.inference import StructuredRequest


def saved_call() -> dict[str, object]:
    return {
        "system": "extract",
        "prompt": '{"c":[{"t":"Товар"}]}',
        "schema": {"type": "object"},
        "response": {"c": []},
        "usage": {"model": "saved", "input_tokens": 10},
    }


def test_replay_returns_saved_output_and_forbids_reusing_response() -> None:
    model = SavedResponse(saved_call())
    request = StructuredRequest("extract", json.dumps({"c": [{"t": "Товар"}]}), {"type": "object"})
    completion = asyncio.run(model.complete(request))
    assert completion.output == {"c": []}
    assert completion.usage.input_tokens == 10
    with pytest.raises(AssertionError, match="exactly one"):
        asyncio.run(model.complete(request))


@pytest.mark.parametrize("changed", ["system", "prompt", "schema"])
def test_replay_refuses_to_evaluate_changed_requests(changed: str) -> None:
    request = StructuredRequest(
        "changed" if changed == "system" else "extract",
        "{}" if changed == "prompt" else '{"c":[{"t":"Товар"}]}',
        {} if changed == "schema" else {"type": "object"},
    )
    model = SavedResponse(saved_call())
    with pytest.raises(AssertionError, match=f"Changed {changed}"):
        asyncio.run(model.complete(request))
    assert not model.used
