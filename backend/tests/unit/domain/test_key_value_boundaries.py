from dataclasses import replace

import pytest

from app.adapter.dataset.demo_catalog import seed_categories
from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import CatalogCandidate, CatalogField, FlowCard
from app.domain.regex_answers import regex_answers


@pytest.mark.parametrize("separator", [". ", "; ", ", ", " "])
def test_inline_known_fields_never_become_one_color_value(separator: str) -> None:
    category = replace(next(c for c in seed_categories() if c.category_id == 761), score=1)
    text = f"Смартфон Fallback ru light 375\nЦвет: синий{separator}Встроенная память: 128 ГБ."
    answers = {a.attribute: a for a in regex_answers(text, category)}
    assert answers["Цвет"].value == answers["Цвет"].quote == "синий"
    assert answers["Встроенная память (ROM)"].value == "128 ГБ"
    assert answers["Встроенная память (ROM)"].quote == "128 ГБ"
    for answer in answers.values():
        assert text[answer.start : answer.end] == answer.quote


@pytest.mark.parametrize("model", ["AB.12.9", "R.O.G. Phone 7", "RT-AX86U Pro (v2.1)"])
def test_dotted_model_and_decimal_quantity_are_preserved(model: str) -> None:
    category = CatalogCandidate(
        1,
        "Товары",
        1,
        (
            CatalogField("Модель", "free", ""),
            CatalogField("Объем", "numeric", "л"),
            CatalogField("Цвет", "categorical", "", ("синий",)),
        ),
    )
    text = f"Товар\nМодель: {model}\nОбъем: 1.75 л. Цвет: синий."
    answers = {a.attribute: a for a in regex_answers(text, category)}
    assert answers["Модель"].value == answers["Модель"].quote == model
    assert answers["Объем"].value == answers["Объем"].quote == "1.75 л"
    assert answers["Цвет"].value == answers["Цвет"].quote == "синий"


def test_categorical_value_cannot_include_another_known_field_declaration() -> None:
    category = replace(next(c for c in seed_categories() if c.category_id == 761), score=1)
    text = "Смартфон\nЦвет: синий. Встроенная память: 128 ГБ."
    value = "синий. Встроенная память: 128 ГБ."
    result = parse_batch(
        {
            "c": [
                {
                    "i": 0,
                    "k": 0,
                    "r": [],
                    "a": [
                        {"f": "Цвет", "v": value, "u": "", "q": value, "r": 0},
                    ],
                }
            ]
        },
        (FlowCard(0, text, (category,)),),
    )[0]
    assert result.items == () and result.extra_fields == ()
    assert result.rejections[0].reason == "field_mismatch"


def test_categorical_key_value_stops_before_an_unlabelled_following_sentence() -> None:
    category = CatalogCandidate(1, "Товары", 1, (CatalogField("Цвет", "categorical", ""),))
    text = "Товар\nЦвет: бирюзовый. Материал корпуса прочный."
    answer = regex_answers(text, category)[0]
    assert answer.value == answer.quote == "бирюзовый"
