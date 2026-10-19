import asyncio
import json
from dataclasses import replace

import pytest
from benchmarks.routing import SavedResponse

from app.domain.inference import StructuredRequest


def test_replay_reuses_only_a_matching_recorded_request() -> None:
    request = StructuredRequest("system", '{"c":[]}', {"type": "object"})
    saved = [
        {
            "system": request.system,
            "prompt": json.dumps({"c": []}),
            "schema": request.schema,
            "response": {"c": []},
            "usage": {"model": "saved", "input_tokens": 10},
            "wall_ms": 20,
        }
    ]
    replay = SavedResponse(saved)
    result = asyncio.run(replay.complete(request))
    assert result.usage.input_tokens == 10
    assert replay.calls == saved
    with pytest.raises(RuntimeError, match="unrecorded"):
        asyncio.run(replay.complete(request))


@pytest.mark.parametrize("part", ["system", "prompt", "schema"])
def test_replay_refuses_stale_responses(part: str) -> None:
    request = StructuredRequest("system", '{"c":[]}', {"type": "object"})
    saved = [{"system": "system", "prompt": request.prompt, "schema": request.schema}]
    if part == "schema":
        changed = replace(request, schema={"type": "array"})
    elif part == "system":
        changed = replace(request, system="changed")
    else:
        changed = replace(request, prompt='{"c":[{}]}')
    with pytest.raises(RuntimeError, match="differs"):
        asyncio.run(SavedResponse(saved).complete(changed))
