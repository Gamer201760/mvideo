import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import CatalogCandidate, CatalogField, Extraction, FlowCard
from app.domain.card_text import SellerParam
from app.domain.evidence_validation import validate_extraction
from app.domain.seller_completion import complete_seller_fields
from benchmarks.files import Row, digest, read_lines, write_json, write_lines
from benchmarks.label_review import validate_review
from benchmarks.metrics import key
from benchmarks.replay import loaded_implementation


def parse_saved(original: Row, card: Row, seller: Row) -> Extraction:
    definition = next(
        (c for c in card["candidates"] if c["category_id"] == original["category_id"]), None
    )
    schema = (
        CatalogCandidate(
            definition["category_id"],
            definition["path"],
            definition["score"],
            tuple(CatalogField(**f) for f in definition["fields"]),
        )
        if definition
        else None
    )
    fields = [f.attribute for f in schema.fields] if schema else []
    raw = {
        "c": [
            {
                "i": 0,
                "k": 0 if schema else original.get("proposed_category"),
                "a": [
                    {
                        "f": fields.index(a["attribute"])
                        if a["attribute"] in fields
                        else a["attribute"],
                        "v": a["value"],
                        "u": a["unit"],
                        "q": a["quote"],
                        "r": a.get("risks", 0),
                    }
                    for a in [*original["items"], *original["extra_fields"]]
                    if a["status"] == "supported"
                ],
                "r": [
                    fields.index(a["attribute"])
                    for a in original["items"]
                    if a["status"] == "ambiguous" and a["attribute"] in fields
                ],
            }
        ]
    }
    result = parse_batch(
        raw, (FlowCard(card["sku_id"], card["text"], (schema,) if schema else ()),)
    )[0]
    result = complete_seller_fields(
        result, schema, card["text"], tuple(SellerParam(**p) for p in seller["seller_params"] or [])
    )
    return validate_extraction(result, schema.fields if schema else (), card["text"], schema)


def recheck(
    prepared: Path, reviews_path: Path, experiment: Path, bundle: Path, output: Path
) -> Row:
    if output.exists():
        raise ValueError("Output exists; preserve prior recheck")
    implementation = loaded_implementation()
    source = json.loads((prepared / "source-audit.json").read_text())
    if (
        digest(experiment / "cards.json")
        != source["source_sha256"]["attribute-flow-compact-main-01/cards.json"]
    ):
        raise ValueError("Historical source changed")
    cards = {r["sku_id"]: r for r in json.loads((experiment / "cards.json").read_text())}
    inputs = {r["sku_id"]: r for r in read_lines(prepared / "review-inputs.jsonl")}
    cases = {r["case_id"]: r for r in read_lines(prepared / "dev-cases.jsonl")}
    reviews = read_lines(reviews_path)
    expected_cases = {r["case_id"] for r in cases.values() if r["selected_for_review"]}
    if (
        len({r["case_id"] for r in reviews}) != len(reviews)
        or {r["case_id"] for r in reviews} != expected_cases
    ):
        raise ValueError("Missing, duplicate or out-of-selection reviews")
    results = {}
    paths = sorted((experiment / "batches").glob("*.json"))
    for path in paths:
        expected_hash = source["source_sha256"].get(
            f"attribute-flow-compact-main-01/batches/{path.name}"
        )
        if expected_hash is None or digest(path) != expected_hash:
            raise ValueError("Historical batch changed")
        for original in json.loads(path.read_text())["initial"]:
            sku = original["sku_id"]
            if sku in inputs:
                if inputs[sku]["text"] != cards[sku]["text"]:
                    raise ValueError("Current and historical input differ")
                results[sku] = parse_saved(original, cards[sku], inputs[sku])
    if digest(bundle / "profiles.json") != source["bundle_artifacts_sha256"]["profiles.json"]:
        raise ValueError("Scoring profiles changed")
    profiles = json.loads((bundle / "profiles.json").read_text())
    transitions: Counter[str] = Counter()
    details = []
    for review in reviews:
        case = cases[review["case_id"]]
        validate_review(review, case, inputs[case["sku_id"]]["text"])
        attribute = case["attribute"]
        profile = profiles.get(attribute, {})
        expected = {key(g["value"], g["unit"], profile, attribute) for g in case["gold"]}
        result = results[case["sku_id"]]
        found = [
            a
            for a in (*result.items, *result.extra_fields)
            if a.attribute == attribute and a.status == "supported"
        ]
        correct = any(
            key(
                a.normalized_value if a.normalized_value is not None else a.value,
                a.normalized_unit if a.normalized_unit is not None else a.unit,
                profile,
                attribute,
            )
            in expected
            for a in found
        )
        rejected = [asdict(r) for r in result.rejections if r.attribute == attribute]
        outcome = (
            "correct"
            if correct
            else "gold_disagreement"
            if found
            else "rejected"
            if rejected
            else "missing"
        )
        transitions[f"{case['outcome']} -> {outcome}"] += 1
        details.append(
            {
                "case_id": case["case_id"],
                "sku_id": case["sku_id"],
                "availability": review["availability"],
                "baseline_cause": review["primary_cause"],
                "before": case["outcome"],
                "after": outcome,
                "rejections": rejected,
            }
        )
    if loaded_implementation() != implementation:
        raise ValueError("Implementation changed during parser recheck")
    write_lines(output / "rechecked-slots.jsonl", details)
    return {
        "scope": "Saved historical proposals parsed again with historical category/schema; current quote relocation, normalization, validation and seller completion; no new extraction calls",
        "new_model_calls": 0,
        "reviewed_slots": len(reviews),
        "transitions": dict(transitions),
        "previously_correct_now_rejected": sum(
            r["before"] == "correct" and r["after"] == "rejected" for r in details
        ),
        "implementation_sha256": implementation,
        "baseline_implementation_sha256": source["implementation_sha256"],
        "reviews_sha256": digest(reviews_path),
        "historical_batches_sha256": {p.name: digest(p) for p in paths},
        "profiles_sha256": digest(bundle / "profiles.json"),
        "limitations": [
            "Not a fresh model run",
            "Historical schemas, categories and proposals are fixed",
            "Later implementation changes require a new recheck",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("prepared", "reviews", "experiment", "bundle", "output", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    write_json(
        args.report, recheck(args.prepared, args.reviews, args.experiment, args.bundle, args.output)
    )


if __name__ == "__main__":
    main()
