from benchmarks.files import Row
from benchmarks.metrics import Counts, evaluate, key, paired_bootstrap
from benchmarks.score import aggregate


def sample() -> Row:
    return {
        "sku_id": 1,
        "category_id": 10,
        "seller": "Seller",
        "train_seller_cards": 0,
        "split": "test",
        "stratum": "rare",
        "sampling_weight": 2,
        "gold": [
            {"attribute": "Вес", "value": "1000", "unit": "г"},
            {"attribute": "Цвет", "value": "красный", "unit": None},
            {"attribute": "Цвет", "value": "красный", "unit": None},
        ],
    }


def prediction(*values: tuple[str, str, str]) -> Row:
    return {
        "sku_id": 1,
        "mode": "hybrid",
        "wall_ms": 25,
        "calls": [],
        "result": {
            "category": {"category_id": 10},
            "extraction": {
                "items": [
                    {"attribute": a, "value": v, "unit": u, "status": "supported"}
                    for a, v, u in values
                ]
            },
        },
    }


PROFILES = {"Вес": {"kind": "numeric"}, "Цвет": {"kind": "categorical"}}


def test_wrong_value_counts_false_positive_and_false_negative() -> None:
    counts, attributes, extra = evaluate(sample(), prediction(("Цвет", "синий", "")), PROFILES)
    assert counts == Counts(tp=0, fp=1, fn=2, filled=1, slots=2)
    assert attributes["Цвет"].fn == 1
    assert extra == 0


def test_units_and_colors_normalize_but_raw_exact_remains_separate() -> None:
    predicted = prediction(("Вес", "1", "кг"), ("Цвет", "красная", ""))
    counts, _, _ = evaluate(sample(), predicted, PROFILES)
    raw, _, _ = evaluate(sample(), predicted, PROFILES, raw=True)
    assert counts == Counts(tp=2, fp=0, fn=0, filled=2, slots=2)
    assert raw == Counts(tp=0, fp=2, fn=2, filled=2, slots=2)


def test_unlabelled_extra_fields_are_counted_separately() -> None:
    counts, _, extra = evaluate(sample(), prediction(("MagSafe", "да", "")), PROFILES)
    assert counts == Counts(tp=0, fp=0, fn=2, slots=2)
    assert extra == 1


def test_failed_request_keeps_all_gold_in_recall_denominator() -> None:
    failed = {
        "sku_id": 1,
        "mode": "hybrid",
        "wall_ms": 120_000,
        "error": "TimeoutError",
        "calls": [],
    }
    report = aggregate([sample()], {1: failed}, PROFILES, {})
    assert report["failed_cards"] == 1
    assert report["normalized"]["fn"] == 2
    assert report["normalized"]["recall"] == 0
    assert report["latency_ms"]["successful_p50"] is None


def test_duplicate_predictions_do_not_inflate_true_positives() -> None:
    counts, _, _ = evaluate(
        sample(), prediction(("Цвет", "красный", ""), ("Цвет", "красный", "")), PROFILES
    )
    assert counts.tp == 1
    assert counts.fn == 1


def test_ranges_and_model_identifiers_are_not_collapsed() -> None:
    assert key("5–10", "см", {"kind": "numeric"}, "Длина") != key(
        "5", "см", {"kind": "numeric"}, "Длина"
    )
    assert key("SM-A556", None, {}, "Модель") != key("SM A556", None, {}, "Модель")
    assert key("5 см упаковка", None, {"kind": "numeric"}, "Длина") != key(
        "5", "см", {"kind": "numeric"}, "Длина"
    )


def test_separate_units_match_embedded_units_without_a_numeric_profile() -> None:
    for profile in ({}, {"kind": "categorical"}, {"kind": "free"}):
        assert key("18", "ГБ", profile, "Объем памяти") == key(
            "18 ГБ", None, profile, "Объем памяти"
        )
        assert key("175", "г/м2", profile, "Плотность материала") == key(
            "175 г/м2", None, profile, "Плотность материала"
        )
        assert key("18", "ГБ", profile, "Объем памяти") != key("18", "МГц", profile, "Объем памяти")


def test_population_weighting_preserves_slot_counts() -> None:
    report = aggregate([sample()], {1: prediction(("Вес", "1", "кг"))}, PROFILES, {"10:Вес": 3})
    assert report["normalized"]["tp"] == 1
    assert report["inverse_sampling_weighted"]["tp"] == 2
    assert report["catalog_metadata_weighted"]["tp"] == 6
    assert report["catalog_metadata_weighted"]["fn"] == 2


def test_paired_stratified_bootstrap_has_zero_delta_for_equal_results() -> None:
    counts = {"tp": 1, "fp": 0, "fn": 1, "filled": 1, "slots": 2}
    report = paired_bootstrap([{"stratum": "rare", "rules": counts, "hybrid": counts}], 42, 30)
    assert report["delta_f1_ci95"] == [0, 0]
