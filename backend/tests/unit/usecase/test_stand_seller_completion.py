import pytest

from app.domain.attribute_flow import CatalogCandidate
from app.domain.card_text import SellerParam
from app.domain.inference import Completion, StructuredRequest, Usage
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput

CATEGORY = CatalogCandidate(7, "Телефоны", 0.8, ())


class Retrieval(CatalogRetrieval):
    def __init__(self) -> None:
        super().__init__({7: CATEGORY}, ())

    def retrieve(self, text: str, k: int = 3) -> tuple[CatalogCandidate, ...]:
        return (CATEGORY,)


class SparseModel:
    async def complete(self, request: StructuredRequest) -> Completion:
        return Completion({"c": [{"i": 0, "k": 0, "a": [], "r": []}]}, Usage("test"))


@pytest.mark.anyio
async def test_explicit_seller_ranges_survive_model_omissions() -> None:
    service = StandAttributeFlow(AttributeFlow(SparseModel(), FlowConfig()), Retrieval())
    result = await service.execute(
        CardInput(
            title="Телефон",
            description="",
            seller_params=(
                SellerParam("Фронтальная камера", "12 - 20", "Мпикс"),
                SellerParam("Поддержка eSIM", "Да"),
            ),
            category_id=None,
        )
    )
    answers = {answer.attribute: answer for answer in result.extraction.extra_fields}
    assert answers["Фронтальная камера"].value == "12 - 20"
    assert answers["Фронтальная камера"].unit == "Мпикс"
    assert answers["Поддержка eSIM"].value == "Да"
    for answer in answers.values():
        assert result.text[answer.start : answer.end] == answer.quote
        assert answer.source == "seller"


@pytest.mark.anyio
async def test_conflicting_seller_fields_are_not_chosen_arbitrarily() -> None:
    service = StandAttributeFlow(AttributeFlow(SparseModel(), FlowConfig()), Retrieval())
    result = await service.execute(
        CardInput(
            title="Телефон",
            description="",
            category_id=None,
            seller_params=(SellerParam("Вес", "1", "кг"), SellerParam("Вес", "2", "кг")),
        )
    )
    assert result.extraction.extra_fields == ()


@pytest.mark.anyio
async def test_seller_unit_already_in_value_is_not_duplicated() -> None:
    service = StandAttributeFlow(AttributeFlow(SparseModel(), FlowConfig()), Retrieval())
    result = await service.execute(
        CardInput(
            title="Телефон",
            description="",
            category_id=None,
            seller_params=(SellerParam("Частота", "120 Гц", "Гц"),),
        )
    )
    answer = result.extraction.extra_fields[0]
    assert answer.value == "120 Гц" and answer.unit == ""
