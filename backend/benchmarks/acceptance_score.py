import argparse
import json
from collections import Counter
from pathlib import Path

from app.domain.acceptance import AcceptancePolicy
from benchmarks.acceptance_reviews import bind_reviews, reviewed_records
from benchmarks.acceptance_statistics import evaluate, validate_reviews
from benchmarks.files import digest, implementation, read_lines, write_json


def score(bundle: Path, predictions: Path, reviews: list[Path], report: Path) -> None:
    if report.exists():
        raise ValueError("Report exists; preserve confirmation runs")
    protocol = json.loads((bundle / "protocol.json").read_text())
    manifest = json.loads((predictions / "manifest.json").read_text())
    current = implementation()
    runtime = {name: sha for name, sha in current.items() if name.startswith("backend/src/app/")}
    frozen = {
        name: sha
        for name, sha in manifest["implementation_sha256"].items()
        if name.startswith("backend/src/app/")
    }
    if runtime != frozen:
        raise ValueError("Runtime changed after inference; confirmation is now development")
    if digest(bundle / "protocol.json") != manifest["protocol_sha256"]:
        raise ValueError("Protocol changed after inference")
    if digest(bundle / "sample.jsonl") != protocol["sample_sha256"]:
        raise ValueError("Frozen sample changed")
    if digest(predictions / "predictions.jsonl") != manifest["predictions_sha256"]:
        raise ValueError("Frozen predictions changed")
    if digest(predictions / "blind-review.jsonl") != manifest["blind_review_sha256"]:
        raise ValueError("Blind review packet changed")
    if len(reviews) != 2 or len({path.resolve() for path in reviews}) != 2:
        raise ValueError("Two separate independent review files are required")
    records = read_lines(predictions / "predictions.jsonl")
    review_protocol = json.loads((predictions / "review-protocol.json").read_text())
    if digest(predictions / "review-subset.jsonl") != review_protocol["review_subset_sha256"]:
        raise ValueError("Review subset changed")
    if review_protocol["predictions_sha256"] != manifest["predictions_sha256"]:
        raise ValueError("Review subset belongs to different predictions")
    if review_protocol["original_blind_packet_sha256"] != manifest["blind_review_sha256"]:
        raise ValueError("Review source packet differs from inference")
    if protocol["policy"]["enabled"] is not True:
        raise ValueError("This study evaluates the enabled fixed acceptance gate")
    policy = AcceptancePolicy(protocol["policy"]["threshold"], protocol["policy"]["enabled"])
    records = reviewed_records(
        records,
        read_lines(predictions / "blind-review.jsonl"),
        read_lines(predictions / "review-subset.jsonl"),
        policy,
    )
    sample = read_lines(bundle / "sample.jsonl")
    if (
        len(sample) != protocol["input_cards"]
        or Counter(r["partition"] for r in sample) != protocol["partition_cards"]
    ):
        raise ValueError("Sample size or partition counts differ from protocol")
    if {r["card_id"] for r in records} != {r["card_id"] for r in sample} or len(records) != len(
        sample
    ):
        raise ValueError("Prediction card set differs from frozen selection")
    partitions = {r["card_id"]: r["partition"] for r in sample}
    if any(row["partition"] != partitions[row["card_id"]] for row in records):
        raise ValueError("Prediction partition changed")
    labels = [read_lines(path) for path in reviews]
    bind_reviews(labels, review_protocol["review_subset_sha256"])
    validate_reviews(records, labels)
    results = {}
    for partition in ["tune", "confirm"]:
        selected = [row for row in records if row["partition"] == partition]
        ids = {row["card_id"] for row in selected}
        subset = [[row for row in rows if row["card_id"] in ids] for rows in labels]
        results[partition] = evaluate(selected, subset, protocol["policy"]["threshold"])
    write_json(
        report,
        {
            "version": "acceptance-study-v1",
            "reference": "Independent agent consensus; not human gold",
            "provider": manifest["provider"],
            "external_model_calls": manifest["external_model_calls"],
            "human_verified": False,
            "protocol_sha256": digest(bundle / "protocol.json"),
            "sample_sha256": digest(bundle / "sample.jsonl"),
            "predictions_sha256": manifest["predictions_sha256"],
            "reviews_sha256": [digest(path) for path in reviews],
            "review_protocol_sha256": digest(predictions / "review-protocol.json"),
            "reviewed_answers": sum(len(row["answers"]) for row in records),
            "supported_answers": sum(row["supported_count"] for row in records),
            "inference_implementation_sha256": manifest["implementation_sha256"],
            "scoring_implementation_sha256": implementation(),
            "partitions": results,
            "admissible_scores": sorted(
                {
                    a["risk"]["score"]
                    for row in records
                    for a in row["answers"]
                    if a["attribute"] in row["automatic"]
                }
            ),
            "policy_change": "None; fixed0.95 gate evaluated, no runtime threshold selected or enabled by this report",
            "limitations": protocol["limitations"],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("bundle", "predictions", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, action="append", required=True)
    args = parser.parse_args()
    score(args.bundle, args.predictions, args.reviews, args.report)


if __name__ == "__main__":
    main()
