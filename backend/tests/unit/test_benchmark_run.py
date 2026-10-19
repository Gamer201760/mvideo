import asyncio
import json

from benchmarks.run import IsolatedRetrieval, RecordedModel

from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.inference import Completion, StructuredRequest, Usage
from app.repository.memory.catalog_retrieval import CatalogRetrieval


class CapturingModel:
    def __init__(self) -> None:
        self.requests: list[StructuredRequest] = []

    async def complete(self, request: StructuredRequest) -> Completion:
        self.requests.append(request)
        return Completion({"c": []}, Usage("test", input_tokens=10, output_tokens=3))


def test_model_ablation_removes_hints_and_retains_same_input_schema_and_system() -> None:
    delegate = CapturingModel()
    model = RecordedModel(delegate, "model")
    payload = {"c": [{"t": "Телефон", "k": [0], "h": [{"v": "red"}]}], "k": [], "f": []}
    request = StructuredRequest("system", json.dumps(payload), {"type": "object"})
    completion = asyncio.run(model.complete(request))
    actual = delegate.requests[0]
    assert "h" not in json.loads(actual.prompt)["c"][0]
    assert json.loads(actual.prompt)["c"][0]["t"] == "Телефон"
    assert actual.system == request.system
    assert actual.schema == request.schema
    assert completion.usage.input_tokens == 10
    assert model.calls[0]["usage"]["model"] == "test"
    assert "h" in json.loads(request.prompt)["c"][0]


def test_hybrid_keeps_hints() -> None:
    delegate = CapturingModel()
    request = StructuredRequest("system", '{"c":[{"h":[]}]}', {})
    asyncio.run(RecordedModel(delegate, "hybrid").complete(request))
    assert delegate.requests == [request]


def test_proposed_category_cannot_modify_shared_retrieval() -> None:
    fields = (CatalogField("Цвет", "categorical", ""),)
    schema = CatalogCandidate(1, "Телефоны / Смартфоны", 0, fields)
    retrieval = CatalogRetrieval({1: schema}, ())
    first = IsolatedRetrieval(retrieval, {1: schema})
    second = IsolatedRetrieval(retrieval, {1: schema})
    proposed = first.add_category("Одежда / Футболки", fields, "Футболка")
    first.remember(proposed, "Футболка")
    assert proposed.category_id == -1
    assert retrieval.added_categories() == ()
    assert second.added_categories() == ()
    first.retrieve("Смартфоны")
    assert len(first.retrieved) == 1
    assert second.retrieved == ()


def test_existing_category_path_resolves_without_mutating_catalog() -> None:
    fields = (CatalogField("Цвет", "categorical", ""),)
    schema = CatalogCandidate(1, "Телефоны / Смартфоны", 0, fields)
    retrieval = CatalogRetrieval({1: schema}, ())
    isolated = IsolatedRetrieval(retrieval, {1: schema})
    assert isolated.add_category(" Телефоны/Смартфоны ", fields, "Телефон") == schema
    assert retrieval.added_categories() == ()
