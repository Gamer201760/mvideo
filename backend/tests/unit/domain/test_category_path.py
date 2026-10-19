import pytest

from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import FlowCard
from app.domain.category_path import category_path


@pytest.mark.parametrize("path", ["", "   ", " / / ", "Техника / ", "/ Дроны", "x" * 201])
def test_invalid_model_category_is_rejected_before_persistence(path: str) -> None:
    with pytest.raises(ValueError):
        parse_batch({"c": [{"i": 0, "k": path, "a": [], "r": []}]}, (FlowCard(1, "Дрон", ()),))


def test_category_separator_spacing_is_canonical() -> None:
    assert category_path(" Техника/  Дроны ") == "Техника / Дроны"
