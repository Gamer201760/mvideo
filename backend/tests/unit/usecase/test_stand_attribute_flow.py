import asyncio
import threading

import pytest

from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.inference import Completion, StructuredRequest, Usage
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput

CATEGORY = CatalogCandidate(7, "Чайники", 0.8, (CatalogField("Цвет", "categorical", ""),))


class Retrieval(CatalogRetrieval):
    def __init__(self) -> None:
        super().__init__({7: CATEGORY}, ())

    def retrieve(self, text: str, k: int = 3) -> tuple[CatalogCandidate, ...]:
        return (CATEGORY,)


class Model:
    async def complete(self, request: StructuredRequest) -> Completion:
        return Completion(
            {
                "c": [
                    {
                        "i": 0,
                        "k": 0,
                        "a": [{"f": 0, "v": "черный", "u": "", "q": "черный"}],
                        "r": [],
                    }
                ]
            },
            Usage("test"),
        )


@pytest.mark.anyio
async def test_preparation_and_extraction_preserve_real_category_and_evidence() -> None:
    service = StandAttributeFlow(AttributeFlow(Model(), FlowConfig()), Retrieval())
    card = CardInput(title="Чайник черный", description="", seller_params=(), category_id=None)
    preview = await service.prepare(card)
    result = await service.execute(card)
    assert preview.candidates == (CATEGORY,)
    assert result.category == CATEGORY
    answer = result.extraction.items[0]
    assert result.text[answer.start : answer.end] == "черный"
    assert result.missing == ()


@pytest.mark.anyio
async def test_retrieval_does_not_block_event_loop() -> None:
    entered, released = threading.Event(), threading.Event()

    class SlowRetrieval(Retrieval):
        def retrieve(self, text: str, k: int = 3) -> tuple[CatalogCandidate, ...]:
            entered.set()
            if not released.wait(timeout=2):
                raise TimeoutError("Event loop could not release retrieval")
            return (CATEGORY,)

    service = StandAttributeFlow(AttributeFlow(Model(), FlowConfig()), SlowRetrieval())
    task = asyncio.create_task(
        service.prepare(
            CardInput(title="Чайник", description="", seller_params=(), category_id=None)
        )
    )
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        assert not task.done()
    finally:
        released.set()
    assert (await task).candidates == (CATEGORY,)
