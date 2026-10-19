from copy import deepcopy
from itertools import combinations

import pytest
from benchmarks.acceptance_duplicates import DuplicateIndex, prefix, similar
from benchmarks.acceptance_reviews import bind_reviews, reviewed_records
from benchmarks.acceptance_statistics import evaluate, lower_bound, validate_reviews
from benchmarks.files import Row

from app.domain.acceptance import AcceptancePolicy


def record() -> Row:
    return {
        "card_id": "C1",
        "category_id": 7,
        "automatic": ["A", "B"],
        "answers": [
            {
                "answer_id": name,
                "attribute": name,
                "value": "alpha",
                "unit": "",
                "quote": "alpha",
                "risk": {
                    "attribute": name,
                    "level": "low",
                    "score": 1.0,
                    "method": "heuristic",
                    "reasons": ["exact_quote", "value_supported", "category_field"],
                },
            }
            for name in ["A", "B"]
        ],
    }


def review(second: bool | None = True, category: bool | None = True) -> list[Row]:
    return [
        {
            "card_id": "C1",
            "full_input_reviewed": True,
            "category_correct": category,
            "answers": [
                {"answer_id": "A", "correct": True, "reason": "Explicit product statement"},
                {"answer_id": "B", "correct": second, "reason": "Full context checked"},
            ],
        }
    ]


def test_exact_card_bound_requires_59_perfect_cards() -> None:
    assert lower_bound(0, 0) is None
    assert lower_bound(0, 10) == 0
    assert lower_bound(59, 59) == pytest.approx(0.05 ** (1 / 59))
    for successes, total, passes in [
        (58, 58, False),
        (59, 59, True),
        (92, 93, True),
        (91, 92, False),
    ]:
        bound = lower_bound(successes, total)
        assert bound is not None
        assert (bound >= 0.95) is passes


@pytest.mark.parametrize("second", [False, None])
def test_one_unconfirmed_field_fails_entire_card_without_dropping_denominator(
    second: bool | None,
) -> None:
    result = evaluate([record()], [review(), review(second)], 0.95)
    assert result["accepted_fields"] == 2
    assert result["confirmed_fields"] == 1
    assert result["nonempty_accepted_cards"] == 1
    assert result["confirmed_cards"] == 0
    assert result["answer_disagreements"] == 1


def test_category_disagreement_invalidates_every_accepted_field() -> None:
    result = evaluate([record()], [review(), review(category=None)], 0.95)
    assert result["confirmed_fields"] == result["confirmed_cards"] == 0
    assert result["accepted_fields"] == 2


def test_empty_card_is_coverage_loss_and_never_success() -> None:
    row = record()
    row["category_id"] = -1
    result = evaluate([row], [review(), review()], 0.95)
    assert result["nonempty_accepted_cards"] == result["confirmed_cards"] == 0
    assert result["card_acceptance_coverage"] == 0
    assert result["one_sided_exact95_card_lower"] is None


def test_missing_or_duplicated_review_cannot_be_ignored() -> None:
    with pytest.raises(ValueError, match="Review cards"):
        validate_reviews([record()], [review(), []])
    with pytest.raises(ValueError, match="Duplicate reviewed answer"):
        bad = review()
        bad[0]["answers"].append(bad[0]["answers"][0])
        validate_reviews([record()], [review(), bad])


def test_reordering_threshold_does_not_change_heuristic_gate() -> None:
    low = evaluate([record()], [review(), review()], 0.95)
    high = evaluate([record()], [review(), review()], 1.0)
    assert low["accepted_fields"] == high["accepted_fields"] == 2


def test_prefix_filter_has_no_false_negatives_at_declared_jaccard() -> None:
    sets = [frozenset(group) for size in range(1, 7) for group in combinations("abcdef", size)]
    for left in sets:
        for right in sets:
            if similar(left, right):
                assert set(prefix(left)) & set(prefix(right))


def test_near_duplicate_index_preserves_different_numeric_content() -> None:
    index = DuplicateIndex(["модель ABC вес 2 кг цвет белый", "модель XYZ вес 20 кг цвет черный"])
    assert index.matches("МОДЕЛЬ ABC вес 2 кг цвет белый") == {0}
    assert index.matches("модель ABC вес 50 кг цвет белый") == set()


def test_exact_duplicate_without_words_is_still_excluded() -> None:
    assert DuplicateIndex(["💻"]).matches("💻") == {0}


@pytest.mark.parametrize("field", ["value", "unit", "quote", "text", "category"])
def test_review_cannot_change_selected_values_with_same_answer_id(field: str) -> None:
    row = record()
    original: Row = {
        "card_id": "C1",
        "text": "alpha",
        "category": "Example",
        "answers": [{k: v for k, v in a.items() if k != "risk"} for a in row["answers"]],
    }
    changed = deepcopy(original)
    if field in {"text", "category"}:
        changed[field] = "changed"
    else:
        changed["answers"][0][field] = "changed"
    with pytest.raises(ValueError, match="text, category or answer"):
        reviewed_records([row], [original], [changed], AcceptancePolicy())


def test_bound_review_rejects_other_packet_and_same_reviewer() -> None:
    rows = [
        [{**r, "reviewer": name, "input_sha256": "current"} for r in review()]
        for name in ["A", "B"]
    ]
    bind_reviews(rows, "current")
    with pytest.raises(ValueError, match="another input"):
        bind_reviews(rows, "changed")
    with pytest.raises(ValueError, match="distinct reviewers"):
        bind_reviews([rows[0], rows[0]], "current")


def test_review_cannot_omit_accepted_field_or_use_null_rationale() -> None:
    row = record()
    original: Row = {
        "card_id": "C1",
        "text": "alpha",
        "category": "Example",
        "answers": [{k: v for k, v in a.items() if k != "risk"} for a in row["answers"]],
    }
    changed = deepcopy(original)
    changed["answers"] = changed["answers"][:1]
    with pytest.raises(ValueError, match="omits accepted"):
        reviewed_records([row], [original], [changed], AcceptancePolicy())
    bad = review()
    bad[0]["answers"][0]["reason"] = None
    with pytest.raises(ValueError, match="Missing answer rationale"):
        validate_reviews([row], [review(), bad])
