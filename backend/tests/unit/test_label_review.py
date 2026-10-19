import copy
import hashlib
from pathlib import Path

import pytest
from benchmarks.files import Row, digest, write_json, write_lines
from benchmarks.label_review import gold_digest, summarize, validate_review


def review_case() -> tuple[Row, Row, str]:
    text = "Прибор\nМощность: 2 кВт"
    case: Row = {
        "case_id": "1:Потребляемая мощность",
        "sku_id": 1,
        "attribute": "Потребляемая мощность",
        "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "gold": [{"attribute": "Потребляемая мощность", "value": "2000", "unit": "Вт"}],
        "outcome": "rejected",
        "rejections": [{"reason": "field_mismatch"}],
    }
    quote = "Мощность: 2 кВт"
    review: Row = {
        **{k: case[k] for k in ("case_id", "sku_id", "attribute", "input_sha256")},
        "catalog_gold_sha256": gold_digest(case),
        "availability": "supported",
        "primary_cause": "false_evidence_rejection",
        "defect_family": "field_alias_or_word_order",
        "evidence": [{"quote": quote, "start": text.index(quote), "end": len(text)}],
        "human_verified": False,
        "reviewer_kind": "agent_full_card_review",
        "full_input_reviewed": True,
        "rationale": "Equivalent watts supported by explicit input power",
    }
    return review, case, text


def test_review_can_support_gold_by_equivalent_units_without_literal_gold() -> None:
    review, case, text = review_case()
    assert "2000" not in text
    validate_review(review, case, text)


@pytest.mark.parametrize("change", ["input", "gold", "quote", "identity", "human", "support"])
def test_review_refuses_stale_or_unverifiable_provenance(change: str) -> None:
    review, case, text = review_case()
    if change == "input":
        text += "\nДругая модификация"
    elif change == "gold":
        case["gold"][0]["value"] = "3000"
    elif change == "quote":
        review["evidence"][0]["start"] += 1
    elif change == "identity":
        review["sku_id"] = 2
    elif change == "human":
        review["human_verified"] = True
    else:
        review["evidence"] = []
    with pytest.raises(ValueError):
        validate_review(review, case, text)


def test_missing_evidence_does_not_automatically_prove_target_absent() -> None:
    review, case, text = review_case()
    case["outcome"] = "missing"
    case["rejections"] = []
    review.update(availability="underdetermined", primary_cause="gold_unavailable", evidence=[])
    validate_review(review, case, text)
    assert review["availability"] == "underdetermined"
    original = copy.deepcopy(review)
    review.update(availability="supported", primary_cause="omission")
    with pytest.raises(ValueError, match="exact evidence"):
        validate_review(review, case, text)
    assert original["availability"] == "underdetermined"


def test_catalog_match_can_still_be_an_unsupported_fill() -> None:
    review, case, text = review_case()
    case["outcome"] = "correct"
    review.update(availability="absent", primary_cause="incorrect_fill", evidence=[])
    validate_review(review, case, text)
    review["primary_cause"] = "none"
    with pytest.raises(ValueError, match="semantic support"):
        validate_review(review, case, text)


@pytest.mark.parametrize("population", ["missing", "duplicate", "outside"])
def test_summary_cannot_silently_change_review_population(tmp_path: Path, population: str) -> None:
    review, case, text = review_case()
    case["selected_for_review"] = True
    prepared = tmp_path / "prepared"
    protocol = tmp_path / "protocol.json"
    write_json(protocol, {"selected_ids": [1]})
    write_json(prepared / "source-audit.json", {"protocol_sha256": digest(protocol)})
    write_lines(prepared / "dev-cases.jsonl", [case])
    write_lines(prepared / "review-inputs.jsonl", [{"sku_id": 1, "text": text}])
    rows = [] if population == "missing" else [review, review]
    if population == "outside":
        rows = [{**review, "case_id": "2:Потребляемая мощность", "sku_id": 2}]
    reviews = tmp_path / "reviews.jsonl"
    write_lines(reviews, rows)
    with pytest.raises(ValueError, match="Missing, duplicate or out-of-selection"):
        summarize(prepared, protocol, reviews, tmp_path / "output")
    assert not (tmp_path / "output").exists()
