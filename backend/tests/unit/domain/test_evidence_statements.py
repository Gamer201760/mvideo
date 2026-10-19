import pytest
from tests.unit.domain.evidence_cases import extract


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit", "schema_unit", "reason"),
    [
        ("Вес", "numeric", "Нагрузка 5 кг", "5", "кг", "кг", "field_unconfirmed"),
        ("Цвет", "categorical", "Цвет: Да", "Да", "", "", "field_type_mismatch"),
        ("Вес", "numeric", "Вес: 20–10 г", "20–10 г", "", "г", "range_mismatch"),
        ("Вес", "numeric", "Вес: 2 кг–500 г", "2 кг–500 г", "", "г", "range_mismatch"),
        (
            "NFC",
            "boolean",
            "NFC поддерживается только с дополнительным модулем",
            "Да",
            "",
            "",
            "conditional_support",
        ),
        (
            "NFC",
            "boolean",
            "NFC поддерживается при покупке модуля",
            "Да",
            "",
            "",
            "conditional_support",
        ),
        (
            "NFC",
            "boolean",
            "NFC поддерживается, если подключен модуль",
            "Да",
            "",
            "",
            "conditional_support",
        ),
        ("Модель", "free", "Модель: AB-12", "AB 12", "", "", "value_unconfirmed"),
        ("Модель", "free", "Модель: AB-12", "AB12", "", "", "value_unconfirmed"),
        ("Модель", "free", "Модель: AB-12 Pro", "AB-12", "", "", "value_unconfirmed"),
        ("Модель", "free", "Модель: Север", "севера", "", "", "value_unconfirmed"),
    ],
)
def test_unrelated_conditional_or_invalid_statements_are_rejected(
    attribute: str, kind: str, text: str, value: str, unit: str, schema_unit: str, reason: str
) -> None:
    _, result = extract(text, attribute, kind, value, unit, text, schema_unit=schema_unit)
    assert not result.items
    assert result.rejections[0].reason == reason


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit", "quote", "schema_unit"),
    [
        ("Цвет", "categorical", "Без NFC красный корпус", "красный", "", "красный", ""),
        (
            "NFC",
            "boolean",
            "NFC поддерживается и Bluetooth отсутствует",
            "Да",
            "",
            "NFC поддерживается",
            "",
        ),
        ("Вес", "numeric", "Телефон B\nУ модели B вес 500 г", "500", "г", "500 г", "г"),
        ("Вес", "numeric", "Телефон\nВес 200 г, вес упаковки 500 г", "200", "г", "200 г", "г"),
        ("Вес", "numeric", "Вес: 500 г–2 кг", "500–2000 г", "", "500 г–2 кг", "г"),
        ("Модель", "free", "Модель: AB-12", "AB-12", "", "AB-12", ""),
        ("Модель", "free", "Модель: AB-12", "ab-12", "", "AB-12", ""),
        ("Модель", "free", "Модель: Север", "Север", "", "Север", ""),
    ],
)
def test_independent_statements_and_exact_identifiers_are_preserved(
    attribute: str, kind: str, text: str, value: str, unit: str, quote: str, schema_unit: str
) -> None:
    _, result = extract(text, attribute, kind, value, unit, quote, schema_unit=schema_unit)
    assert len(result.items) == 1, result.validation_errors
    assert not result.rejections


@pytest.mark.parametrize(
    "condition", ["только с дополнительным модулем", ", если подключен модуль"]
)
def test_short_quote_cannot_drop_a_support_condition(condition: str) -> None:
    text = "NFC поддерживается " + condition
    _, result = extract(text, "NFC", "boolean", "Да", "", "NFC поддерживается")
    assert not result.items
    assert result.rejections[0].reason == "conditional_support"
