import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from benchmarks.files import Row, digest, read_lines, write_json, write_lines

AVAILABILITY = frozenset({"supported", "absent", "underdetermined", "conflicting"})
CAUSES = frozenset(
    {
        "none",
        "gold_unavailable",
        "input_conflict",
        "false_evidence_rejection",
        "matching_limitation",
        "omission",
        "coarse_proposal",
        "incorrect_proposal",
        "truncated_identifier",
        "incorrect_fill",
        "normalization_error",
        "category_error",
    }
)


DEFECT_FAMILIES = frozenset(
    {
        "field_alias_or_word_order",
        "paraphrase",
        "colon_inside_value",
        "foreign_context",
        "numeric_identifier",
        "maximum_endpoint",
        "list_of_flags",
    }
)


def gold_digest(case: Row) -> str:
    return hashlib.sha256(
        json.dumps(case["gold"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def validate_review(review: Row, case: Row, text: str) -> None:
    for name in ("case_id", "sku_id", "attribute", "input_sha256"):
        if review[name] != case[name]:
            raise ValueError(f"Review identity mismatch: {name}")
    if hashlib.sha256(text.encode()).hexdigest() != case["input_sha256"]:
        raise ValueError("Review input changed")
    if review["catalog_gold_sha256"] != gold_digest(case):
        raise ValueError("Review gold target changed")
    if review["availability"] not in AVAILABILITY or review["primary_cause"] not in CAUSES:
        raise ValueError("Unknown review classification")
    if review["human_verified"] is not False or review["reviewer_kind"] != "agent_full_card_review":
        raise ValueError("Agent review cannot be promoted to independent human gold")
    if review["full_input_reviewed"] is not True or not review["rationale"].strip():
        raise ValueError("Full input review and rationale required")
    if review["availability"] == "supported" and not review["evidence"]:
        raise ValueError("Supported review requires exact evidence")
    if review["availability"] == "absent" and review["evidence"]:
        raise ValueError("Absent target cannot have confirming evidence")
    for span in review["evidence"]:
        if (
            span["start"] < 0
            or not span["quote"]
            or text[span["start"] : span["end"]] != span["quote"]
        ):
            raise ValueError("Invalid review evidence offsets")
    cause = review["primary_cause"]
    if cause == "none" and (case["outcome"] != "correct" or review["availability"] != "supported"):
        raise ValueError("A correct catalog match must also have semantic support")
    if (
        cause
        in {
            "false_evidence_rejection",
            "omission",
            "coarse_proposal",
            "truncated_identifier",
            "incorrect_proposal",
        }
        and review["availability"] != "supported"
    ):
        raise ValueError("Extraction defect requires supported gold")
    if cause == "false_evidence_rejection" and not case["rejections"]:
        raise ValueError("False rejection requires a recorded rejection")
    if cause == "false_evidence_rejection" and review.get("defect_family") not in DEFECT_FAMILIES:
        raise ValueError("False rejection requires an explicit defect family")
    if cause == "gold_unavailable" and review["availability"] not in {"absent", "underdetermined"}:
        raise ValueError("Unavailable gold must remain distinct from input conflict")


def summarize(prepared: Path, protocol_path: Path, reviews_path: Path, output: Path) -> Row:
    if output.exists():
        raise ValueError("Private output exists; preserve previous review")
    protocol = json.loads(protocol_path.read_text())
    source = json.loads((prepared / "source-audit.json").read_text())
    if digest(protocol_path) != source["protocol_sha256"]:
        raise ValueError("Review protocol changed")
    cases = read_lines(prepared / "dev-cases.jsonl")
    selected = {r["case_id"]: r for r in cases if r["selected_for_review"]}
    if {r["sku_id"] for r in selected.values()} != set(protocol["selected_ids"]):
        raise ValueError("Reviewed population differs from frozen selection")
    cards = {r["sku_id"]: r for r in read_lines(prepared / "review-inputs.jsonl")}
    reviews = read_lines(reviews_path)
    by_id = {r["case_id"]: r for r in reviews}
    if len(by_id) != len(reviews) or set(by_id) != set(selected):
        raise ValueError("Missing, duplicate or out-of-selection reviews")
    for review in reviews:
        validate_review(review, selected[review["case_id"]], cards[review["sku_id"]]["text"])
    write_lines(
        output / "annotated-dev.jsonl",
        (
            {
                **case,
                "review": by_id.get(case["case_id"]),
                "review_status": "agent_reviewed" if case["case_id"] in by_id else "pending",
            }
            for case in cases
        ),
    )
    artifacts = {
        name: digest(prepared / name)
        for name in (
            "source-audit.json",
            "train-labels.jsonl",
            "dev-cases.jsonl",
            "dev-results.jsonl",
            "review-inputs.jsonl",
        )
    }
    causes = Counter(r["primary_cause"] for r in reviews)
    return {
        "version": "label-reuse-audit-v1",
        "scope": protocol["scope"],
        "new_model_calls": 0,
        "source_alignment": source,
        "review_implementation_sha256": {
            name: digest(Path(__file__).parent / name)
            for name in ("label_inputs.py", "label_prepare.py", "label_review.py")
        },
        "selection": {
            k: protocol[k] for k in ("selection", "review_cards", "scorer_policy", "control_policy")
        },
        "protocol_sha256": digest(protocol_path),
        "reviews_sha256": digest(reviews_path),
        "private_artifacts_sha256": artifacts,
        "reviewed_cards": len(cards),
        "reviewed_slots": len(reviews),
        "unreviewed_dev_slots": len(cases) - len(reviews),
        "availability": dict(Counter(r["availability"] for r in reviews)),
        "causes": dict(causes),
        "false_rejection_families": dict(
            Counter(
                r["defect_family"]
                for r in reviews
                if r["primary_cause"] == "false_evidence_rejection"
            )
        ),
        "cause_cards": {
            cause: len({r["sku_id"] for r in reviews if r["primary_cause"] == cause})
            for cause in causes
        },
        "availability_by_outcome": dict(
            Counter(f"{selected[r['case_id']]['outcome']} / {r['availability']}" for r in reviews)
        ),
        "all_dev_outcomes": dict(Counter(r["outcome"] for r in cases)),
        "reviewer_kind": "agent_full_card_review",
        "human_verified_slots": 0,
        "limitations": [
            "Only the preselected 30 cards / 193 slots received full-card agent review; other dev slots remain pending",
            "Existing train labels remain machine-reviewed candidates, not independent human ground truth",
            "Legacy dev diagnostics and exact quote matches do not establish semantic support",
            "Cases use historical saved proposals and schemas with current validation, normalization and seller completion",
            "Counts are descriptive on reused dev, not a new F1 measurement or population error rates",
            "Some false rejections concern grounded proposals with different granularity than catalog gold; fixes may not improve F1",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("prepared", "protocol", "reviews", "private-output", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.prepared, args.protocol, args.reviews, args.private_output)
    write_json(args.report, report)


if __name__ == "__main__":
    main()
