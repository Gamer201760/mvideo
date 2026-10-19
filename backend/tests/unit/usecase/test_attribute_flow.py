import asyncio
import json

import pytest

from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import CatalogCandidate, CatalogField, FlowCard
from app.domain.inference import Completion, Effort, StructuredRequest, Usage
from app.usecase.attribute_flow import AttributeFlow, FlowConfig, batches
from app.usecase.attribute_flow_contract import make_request


def card(sku_id: int = 4) -> FlowCard:
    return FlowCard(
        sku_id,
        "Чайник черный, объем 1700 мл",
        (
            CatalogCandidate(
                100,
                "Чайники",
                0.8,
                (
                    CatalogField("Цвет", "categorical", ""),
                    CatalogField("Объем", "numeric", "л"),
                ),
            ),
        ),
    )


def output(index: int = 0) -> dict[str, object]:
    return {
        "c": [
            {
                "i": index,
                "k": 0,
                "a": [
                    {"f": 0, "v": "черный", "u": "", "q": "черный"},
                ],
                "r": [],
            }
        ]
    }


def test_compact_mapping_roundtrip_and_exact_quote() -> None:
    request = make_request((card(),))
    payload = json.loads(request.prompt)
    result = parse_batch(output(), (card(),))[0]
    assert request.effort is Effort.LOW
    assert payload["f"] == ["Цвет", "Объем"]
    assert "sku_id" not in request.prompt
    assert result.sku_id == 4 and result.category_id == 100
    answer = result.items[0]
    assert card().text[answer.start : answer.end] == "черный"
    assert answer.attribute == "Цвет"
    previous = json.loads(make_request((card(),), (result,)).prompt)
    assert previous["b"][0]["a"][0]["f"] == 0


def test_reordered_batch_and_dictionary_ids_are_restored() -> None:
    other = FlowCard(
        8,
        "Стол из стали",
        (CatalogCandidate(200, "Столы", 0.7, (CatalogField("Материал", "free", ""),)),),
    )
    raw = {
        "c": [
            {"i": 1, "k": 1, "a": [{"f": 2, "v": "сталь", "u": "", "q": "из стали"}], "r": []},
            {"i": 0, "k": 0, "a": [], "r": []},
        ]
    }
    result = parse_batch(raw, (card(), other))
    assert [r.sku_id for r in result] == [4, 8]
    assert result[1].items[0].attribute == "Материал"


@pytest.mark.parametrize(
    "raw",
    [
        {"c": []},
        {"c": [{"i": 0}, {"i": 0}]},
        {"c": [{"i": 0, "k": 44, "a": [], "r": []}]},
        {"c": [{"i": 0, "k": None, "a": [], "r": [0]}]},
    ],
)
def test_malformed_identity_or_category_is_rejected(raw: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        parse_batch(raw, (card(),))


def test_invalid_evidence_and_conflicting_duplicates_never_accepted() -> None:
    raw = {
        "c": [
            {
                "i": 0,
                "k": 0,
                "a": [
                    {"f": 0, "v": "белый", "u": "", "q": "белый"},
                    {"f": 1, "v": "1700", "u": "мл", "q": "1700 мл"},
                    {"f": 1, "v": "1", "u": "л", "q": "объем"},
                ],
                "r": [],
            }
        ]
    }
    result = parse_batch(raw, (card(),))[0]
    assert not result.items and result.review
    assert len(result.validation_errors) == 2


def test_new_fields_stay_separate_from_catalog() -> None:
    raw = {
        "c": [
            {
                "i": 0,
                "k": 0,
                "a": [
                    {"f": "Описание цвета", "v": "черный", "u": "", "q": "черный"},
                ],
                "r": [1],
            }
        ]
    }
    result = parse_batch(raw, (card(),))[0]
    assert result.extra_fields[0].attribute == "Описание цвета"
    assert result.items[0].status == "ambiguous" and result.review


class Model:
    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.requests: list[StructuredRequest] = []

    async def complete(self, request: StructuredRequest) -> Completion:
        self.requests.append(request)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.01)
            payload = json.loads(request.prompt)
            return Completion(
                {
                    "c": [
                        {"i": i, "k": 0, "a": [], "r": [] if "b" in payload else [0]}
                        for i in range(len(payload["c"]))
                    ]
                },
                Usage("test-port"),
            )
        finally:
            self.active -= 1


def test_concurrency_bound_and_conditional_audit_share_one_gate() -> None:
    async def run() -> None:
        model = Model()
        flow = AttributeFlow(model, FlowConfig(batch_size=2, concurrency=2, audit="conditional"))
        result = await flow.run([card(i) for i in range(5)])
        assert len(model.requests) == 6
        assert model.peak == 2
        assert len(result) == 3
        assert all(len(r.calls) == 2 for r in result)
        assert all(r.final_ready_ms >= r.first_ready_ms for r in result)
        assert all(not item.review for r in result for item in r.final)

    asyncio.run(run())


def test_off_disables_second_pass_and_timeout_does_not_hang() -> None:
    async def run() -> None:
        model = Model()
        result = await AttributeFlow(model, FlowConfig(audit="off")).run([card()])
        assert len(model.requests) == 1 and len(result[0].calls) == 1
        timed = await AttributeFlow(model, FlowConfig(timeout_s=0.001)).run([card()])
        assert not timed[0].initial and "TimeoutError" in (timed[0].calls[0].error or "")

    asyncio.run(run())


def test_batch_character_limit_splits_without_truncating_text() -> None:
    groups = batches([card(1), card(2)], FlowConfig(batch_size=10, max_batch_chars=1))
    assert len(groups) == 2
    assert groups[0][0].text == card().text


def test_normalization_converts_units_and_preserves_raw_value_and_quote() -> None:
    raw = {
        "c": [
            {
                "i": 0,
                "k": 0,
                "a": [
                    {"f": 1, "v": "1700", "u": "мл", "q": "1700 мл"},
                ],
                "r": [],
            }
        ]
    }
    answer = parse_batch(raw, (card(),))[0].items[0]
    assert answer.normalized_value == "1.7" and answer.normalized_unit == "л"
    assert answer.value == "1700" and answer.unit == "мл" and answer.quote == "1700 мл"
