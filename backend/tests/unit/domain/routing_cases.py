from app.domain.attribute_evidence import parse_answer
from app.domain.attribute_flow import CatalogCandidate, CatalogField, FlowCard


def complete_card(sku: int = 1) -> FlowCard:
    text = "Товар\nЦвет: красный\nВес: 500 г"
    category = CatalogCandidate(
        7,
        "Товары",
        0.9,
        (
            CatalogField("Цвет", "categorical", ""),
            CatalogField("Вес", "numeric", "г"),
        ),
    )
    answers = tuple(
        parse_answer({"v": value, "u": unit, "q": quote}, name, text)
        for name, value, unit, quote in (
            ("Цвет", "красный", "", "Цвет: красный"),
            ("Вес", "500", "г", "Вес: 500 г"),
        )
    )
    return FlowCard(sku, text, (category,), answers)
