from dataclasses import replace

import pytest

from app.adapter.dataset.demo_catalog import seed_categories
from app.adapter.llm.output_validation import validate_output
from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import FlowCard
from app.usecase.attribute_flow_contract import SCHEMA

TEXT = (
    "Смартфон Ладога L1\nКорпус синего цвета. Встроенная память составляет 128 ГБ. "
    "Емкость аккумулятора не указана."
)


def phone_card() -> FlowCard:
    category = replace(next(c for c in seed_categories() if c.category_id == 761), score=1)
    return FlowCard(0, TEXT, (category,))


@pytest.mark.parametrize("named_fields", [False, True])
def test_valid_named_or_indexed_fields_preserve_grounded_phone_answers(named_fields: bool) -> None:
    card = phone_card()
    output = {
        "c": [
            {
                "i": 0,
                "k": 0,
                "r": [],
                "a": [
                    {"f": "Модель" if named_fields else 1, "v": "L1", "u": "", "q": "L1", "r": 0},
                    {
                        "f": "Цвет" if named_fields else 5,
                        "v": "синий",
                        "u": "",
                        "q": "синего",
                        "r": 0,
                    },
                    {
                        "f": "Встроенная память (ROM)" if named_fields else 2,
                        "v": "128 ГБ",
                        "u": "ГБ",
                        "q": "128 ГБ",
                        "r": 0,
                    },
                ],
            }
        ],
    }
    validate_output(output, SCHEMA)
    result = parse_batch(output, (card,))[0]
    assert {a.attribute for a in result.items} == {"Модель", "Цвет", "Встроенная память (ROM)"}
    memory = next(a for a in result.items if a.attribute == "Встроенная память (ROM)")
    assert memory.normalized_value == "128" and memory.normalized_unit == "гб"
    assert result.extra_fields == () and result.rejections == ()
    assert result.validation_errors == ()
    for answer in result.items:
        assert card.text[answer.start : answer.end] == answer.quote


def test_named_and_indexed_duplicates_are_rejected_as_the_same_field() -> None:
    output = {
        "c": [
            {
                "i": 0,
                "k": 0,
                "r": [],
                "a": [
                    {"f": 5, "v": "синий", "u": "", "q": "синего цвета", "r": 0},
                    {"f": "Цвет", "v": "синий", "u": "", "q": "синего цвета", "r": 0},
                ],
            }
        ]
    }
    result = parse_batch(output, (phone_card(),))[0]
    assert result.items == () and result.extra_fields == ()
    assert result.validation_errors == ("duplicate attribute Цвет",)


@pytest.mark.parametrize(
    ("field", "value", "unit", "quote"),
    [
        ("Цвет", "красный", "", "синего цвета"),
        ("Емкость аккумулятора", "128", "мАч", "128 ГБ"),
        ("Емкость аккумулятора", "Да", "", "Емкость аккумулятора не указана"),
        ("Встроенная память (ROM)", "128", "ГБ", "Емкость аккумулятора не указана"),
    ],
)
def test_named_schema_fields_keep_existing_evidence_guards(
    field: str, value: str, unit: str, quote: str
) -> None:
    output = {
        "c": [
            {
                "i": 0,
                "k": 0,
                "r": [],
                "a": [
                    {"f": field, "v": value, "u": unit, "q": quote, "r": 0},
                ],
            }
        ]
    }
    result = parse_batch(output, (phone_card(),))[0]
    assert result.items == () and result.extra_fields == ()
    assert result.rejections


@pytest.mark.parametrize(
    ("description", "memory"),
    [
        ("Оперативная память составляет 128 ГБ", "Встроенная память (ROM)"),
        ("Встроенная память составляет 128 ГБ", "Оперативная память (RAM)"),
    ],
)
def test_memory_acronym_alias_does_not_swap_storage_and_ram(description: str, memory: str) -> None:
    category = replace(
        phone_card().candidates[0],
        fields=(replace(phone_card().candidates[0].fields[2], attribute=memory),),
    )
    card = FlowCard(0, description, (category,))
    result = parse_batch(
        {
            "c": [
                {
                    "i": 0,
                    "k": 0,
                    "a": [{"f": memory, "v": "128", "u": "ГБ", "q": "128 ГБ", "r": 0}],
                    "r": [],
                }
            ]
        },
        (card,),
    )[0]
    assert result.items == ()
    assert result.rejections
