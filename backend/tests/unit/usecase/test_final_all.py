from collections import Counter

from app.domain.fusion import BASELINE, DECISION, KNOWN, NEW, RANKER, TWIN, FusionRules, Rule
from app.usecase.final_all import fuse_record


def _value(value: str, confidence: float, source: str = "dictionary",
           sources: tuple[str, ...] = ("dictionary",)) -> dict[str, object]:
    return {"value": value, "confidence": confidence, "source": source, "sources": list(sources),
            "evidence": value, "start": 0, "end": len(value)}


def _record(category: int | None, split: str | None, **attributes: object) -> dict[str, object]:
    return {"sku_id": 1, "category_id": category, "split": split, "attributes": attributes,
            "review": {}}


RULES = FusionRules({KNOWN: Rule(RANKER, True), NEW: Rule(DECISION, False)},
                    {("Модель", KNOWN): Rule(BASELINE, False)})


def _same(_: str, confidence: float) -> float:
    return confidence


def test_known_category_uses_attribute_rule_and_twin_fill() -> None:
    ranker = _record(761, "test", Модель=_value("A5", 0.9))
    baseline = _record(761, "test", Модель=_value("A55", 0.8))
    twin = _record(761, "test", Вес=_value("200 г", 0.7, "catalog_twin", ("catalog_twin",)))
    used: Counter[str] = Counter()
    fused = fuse_record(ranker, baseline, None, twin, RULES, _same, 0.3, used)
    attributes = fused["attributes"]
    assert isinstance(attributes, dict)
    assert attributes["Модель"]["value"] == "A55"
    assert attributes["Вес"]["stage"] == TWIN
    assert used[BASELINE] == 1


def test_new_category_respects_decision_refusal_and_threshold() -> None:
    ranker = _record(None, None, Цвет=_value("синий", 0.9), Бренд=_value("Acme", 0.2))
    baseline = _record(None, None, Цвет=_value("синий", 0.8), Бренд=_value("Acme", 0.6))
    decision = _record(None, None, Бренд=_value("Acme", 0.2, sources=("decision",)))
    fused = fuse_record(ranker, baseline, decision, None, RULES, _same, 0.3, Counter())
    assert fused["category_mode"] == NEW
    assert fused["attributes"] == {}
    review = fused["review"]
    assert isinstance(review, dict) and review["Бренд"]["stage"] == DECISION
