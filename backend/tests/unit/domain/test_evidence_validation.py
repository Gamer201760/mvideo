import pytest
from tests.unit.domain.evidence_cases import extract


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit", "quote"),
    [
        ("Цвет", "categorical", "Цвет: красный", "синий", "", "Цвет: красный"),
        ("Цвет", "categorical", "Красный корпус", "синий", "", "Красный корпус"),
        ("Цвет", "categorical", "Цвет: красный", "крас", "", "Цвет: красный"),
        ("Цвет", "categorical", "Цвет: не красный", "красный", "", "красный"),
        ("NFC", "boolean", "NFC не поддерживается", "Да", "", "поддерживается"),
        ("NFC", "boolean", "Без NFC", "Да", "", "NFC"),
        ("NFC", "boolean", "NFC отсутствует", "Да", "", "NFC отсутствует"),
        ("NFC", "boolean", "NFC поддерживается", "Нет", "", "NFC поддерживается"),
        ("NFC", "boolean", "Цвет: красный", "Да", "", "Цвет: красный"),
        ("NFC", "boolean", "NFC: неизвестно", "Да", "", "NFC: неизвестно"),
        ("Вес", "numeric", "Вес: 500 г", "500", "кг", "500 г"),
        ("Вес", "numeric", "Вес: 500 г", "500", "л", "500 г"),
        ("Вес", "numeric", "Вес: 500 г", "600", "г", "500 г"),
        ("Вес", "numeric", "Вес: 500 г", "500", "г", "500"),
        ("Вес", "numeric", "Вес: 500 кг/м", "500", "кг", "500 кг/м"),
        ("Время", "numeric", "Время: до 20 ч", "20", "ч", "20"),
        ("Время", "numeric", "Время: от 10 до 20 ч", "20", "ч", "от 10 до 20 ч"),
        ("Время", "numeric", "Время: 10–20 ч", "20", "ч", "10–20 ч"),
        ("Время", "numeric", "Время: 10–20 ч", "15", "ч", "10–20 ч"),
        ("Вес", "numeric", "Вес: 10–20 г", "10–20", "кг", "10–20 г"),
        ("Время", "numeric", "Время: от 10 до 20 ч", "до 20 ч", "", "от 10 до 20 ч"),
        ("Вес", "numeric", "Вес упаковки: 500 г", "500", "г", "500 г"),
        ("Диагональ", "numeric", "Совместим с экраном 6 дюймов", "6", '"', "6 дюймов"),
        ("Цвет", "categorical", "Чехол красный", "красный", "", "красный"),
        ("Вес", "numeric", "У модели B вес 500 г", "500", "г", "500 г"),
        ("Цвет", "categorical", "Цвет: красный\nЦвет: синий", "красный", "", "Цвет: красный"),
        ("Вес", "numeric", "Вес: 1 кг\nВес: 2 кг", "1", "кг", "Вес: 1 кг"),
    ],
)
def test_contradictions_are_omitted_before_scoring(
    attribute: str, kind: str, text: str, value: str, unit: str, quote: str
) -> None:
    _, result = extract(text, attribute, kind, value, unit, quote)
    assert result.items == ()
    assert result.review and result.validation_errors


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit", "quote"),
    [
        ("Цвет", "categorical", "Цвет: красная", "красный", "", "Цвет: красная"),
        ("Цвет", "categorical", "Цвет: red", "красный", "", "red"),
        ("Вес", "numeric", "Вес: 500 г", "0.5", "кг", "500 г"),
        ("Длина", "numeric", "Длина: 2 см", "20", "мм", "2 см"),
        ("Время", "numeric", "Время: до 20 ч", "до 20 ч", "", "до 20 ч"),
        ("Время", "numeric", "Время: 10–20 ч", "10 - 20", "ч", "10–20 ч"),
        ("NFC", "boolean", "NFC не поддерживается", "нет", "", "NFC не поддерживается"),
        ("NFC", "boolean", "Товар не имеет NFC", "нет", "", "Товар не имеет NFC"),
        ("NFC", "boolean", "NFC: Да", "да", "", "Да"),
        ("NFC", "boolean", "NFC поддерживается", "Да", "", "NFC поддерживается"),
        ("Вес", "numeric", "Вес: 500 г. NFC отсутствует", "500", "г", "500 г"),
        ("Вес", "numeric", "Вес: 500 г; коробка: 1 кг", "500", "г", "500 г"),
        ("Вес", "numeric", "Вес: 1000 г\nВес: 1 кг", "1", "кг", "Вес: 1 кг"),
        ("Вес упаковки", "numeric", "Вес упаковки: 500 г", "500", "г", "500 г"),
        ("Материал", "free", "Стол из стали", "сталь", "", "из стали"),
    ],
)
def test_supported_normalizations_keep_original_quote(
    attribute: str, kind: str, text: str, value: str, unit: str, quote: str
) -> None:
    card, result = extract(text, attribute, kind, value, unit, quote)
    assert len(result.items) == 1, result.validation_errors
    answer = result.items[0]
    assert answer.status == "supported"
    assert card.text[answer.start : answer.end] == answer.quote == quote


@pytest.mark.parametrize("flags", [1, 2, 3])
def test_scope_and_conflict_flags_cannot_pass_with_exact_value(flags: int) -> None:
    _, result = extract(
        "Цвет: красный", "Цвет", "categorical", "красный", "", "красный", flags=flags
    )
    assert not result.items and result.review


def test_extra_fields_also_reject_other_object_measurements() -> None:
    _, result = extract("Вес упаковки: 500 г", "Вес", "numeric", "500", "г", "500 г", extra=True)
    assert not result.extra_fields and result.validation_errors


def test_new_color_field_cannot_bypass_validation_without_a_schema() -> None:
    _, result = extract("Красный корпус", "Цвет", "free", "синий", "", "Красный корпус", extra=True)
    assert not result.extra_fields and result.validation_errors


def test_schema_unit_prevents_relabelling_a_quantity() -> None:
    _, result = extract("Вес: 1 л", "Вес", "numeric", "1", "л", "1 л", schema_unit="кг")
    assert not result.items and result.validation_errors


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit", "quote", "schema_unit"),
    [
        ("Материал", "free", "Корпус пластиковый", "сталь", "", "Корпус пластиковый", ""),
        ("NFC", "boolean", "Bluetooth: Да", "Да", "", "Bluetooth: Да", ""),
        ("NFC", "boolean", "Bluetooth отсутствует", "нет", "", "Bluetooth отсутствует", ""),
        ("NFC", "boolean", "NFC поддерживается", "банан", "", "NFC поддерживается", ""),
        ("Вес", "numeric", "Вес: 1 кг; Нагрузка: 5 кг", "5", "кг", "Нагрузка: 5 кг", "кг"),
        ("Вес", "numeric", "Вес: не 500 г", "500", "г", "500 г", "г"),
        ("Вес", "numeric", "Вес: 10–20 л", "10–20 л", "", "10–20 л", "кг"),
        ("Температура", "numeric", "Температура: −5 °с", "5", "°с", "5 °с", "°с"),
        ("Вес", "numeric", "Другая модель, вес 500 г", "500", "г", "500 г", "г"),
        (
            "Тип",
            "categorical",
            "Адаптер USB-C на HDMI",
            "HDMI на USB-C",
            "",
            "Адаптер USB-C на HDMI",
            "",
        ),
        ("Цвет", "categorical", "Телефон с чехлом\nЧехол красный", "красный", "", "красный", ""),
    ],
)
def test_reviewed_bypasses_do_not_return_supported_values(
    attribute: str, kind: str, text: str, value: str, unit: str, quote: str, schema_unit: str
) -> None:
    _, result = extract(text, attribute, kind, value, unit, quote, schema_unit=schema_unit)
    assert not result.items
    assert len(result.rejections) == 1
    assert result.rejections[0].attribute == attribute
    assert result.rejections[0].quote == quote


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit", "quote", "schema_unit"),
    [
        ("Цвет", "categorical", "Чехол красный\nЗащитный чехол", "красный", "", "красный", ""),
        (
            "Цвет",
            "categorical",
            "Защитный чехол\nЦвет чехла: красный",
            "красный",
            "",
            "красный",
            "",
        ),
        ("Цвет", "categorical", "Красный корпус без NFC", "красный", "", "Красный корпус", ""),
        ("Цвет", "categorical", "Не синий, а красный корпус", "красный", "", "красный", ""),
        ("Материал", "free", "Корпус пластиковый", "пластик", "", "Корпус пластиковый", ""),
        ("Вес", "numeric", "Вес: 10–20 г", "0.01–0.02 кг", "", "10–20 г", "кг"),
        ("Температура", "numeric", "Температура: −5 °с", "-5", "°с", "−5 °с", "°с"),
    ],
)
def test_valid_values_survive_context_and_quantity_checks(
    attribute: str, kind: str, text: str, value: str, unit: str, quote: str, schema_unit: str
) -> None:
    _, result = extract(text, attribute, kind, value, unit, quote, schema_unit=schema_unit)
    assert len(result.items) == 1, result.validation_errors
    assert result.rejections == ()


def test_repeated_quote_selects_occurrence_in_the_product_context() -> None:
    text = "Телефон\nЧехол красный. Корпус красный"
    _, result = extract(text, "Цвет", "categorical", "красный", "", "красный")
    assert result.items[0].start == text.rfind("красный")
    assert result.rejections == ()
