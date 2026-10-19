import argparse
import hashlib
import inspect
import json
from collections import defaultdict
from dataclasses import asdict, replace
from pathlib import Path

from app.domain.attribute_flow import CatalogCandidate, CatalogField, Extraction, FieldAnswer
from app.domain.attribute_normalization import normalize_answer
from app.domain.card_text import SellerParam
from app.domain.evidence_validation import validate_extraction
from app.domain.seller_completion import complete_seller_fields
from benchmarks.dataset import required_fields
from benchmarks.files import Row, digest, write_json, write_lines
from benchmarks.label_inputs import align_sources, diagnostics_by_pair
from benchmarks.metrics import key
from benchmarks.replay import loaded_implementation


def prepare(experiments: Path, data: Path, bundle: Path, protocol_path: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Output exists; preserve previous audit")
    loaded_before = loaded_implementation()
    registry, summary = align_sources(experiments, data, bundle)
    protocol = json.loads(protocol_path.read_text())
    if (
        digest(experiments / "attribute-flow-compact-main-01/cards.json")
        != protocol["development_cards_sha256"]
    ):
        raise ValueError("Development source changed after selection")
    selected = set(protocol["selected_ids"])
    if len(selected) != protocol["review_cards"] or not selected <= set(registry["dev"]):
        raise ValueError("Invalid review selection")
    required, _ = required_fields(data)
    targets_path = experiments / "strong-extraction-01/requests.json"
    targets = {r["sku_id"]: r["attributes"] for r in json.loads(targets_path.read_text())}
    summary["source_sha256"]["strong-extraction-01/requests.json"] = digest(targets_path)
    summary["target_policy"] = (
        "Frozen historical dev requested attributes with current processed gold; not the benchmark's required-slot population"
    )
    profiles = json.loads((bundle / "profiles.json").read_text())
    diagnostic = diagnostics_by_pair(registry)
    results = {}
    proposals = {}
    answer_rows = []
    for path in sorted((experiments / "attribute-flow-compact-main-01/batches").glob("*.json")):
        summary["source_sha256"][f"attribute-flow-compact-main-01/batches/{path.name}"] = digest(
            path
        )
        for original in json.loads(path.read_text())["initial"]:
            sku = original["sku_id"]
            proposals[sku] = [*original["items"], *original["extra_fields"]]
            card = registry["dev"][sku]
            category = next(
                (c for c in card["candidates"] if c["category_id"] == original["category_id"]), None
            )
            definitions = (
                {f["attribute"]: CatalogField(**f) for f in category["fields"]} if category else {}
            )
            schema = (
                CatalogCandidate(
                    category["category_id"],
                    category["path"],
                    category["score"],
                    tuple(definitions.values()),
                )
                if category
                else None
            )
            validation_options: Row = (
                {"category": schema}
                if "category" in inspect.signature(validate_extraction).parameters
                else {}
            )
            answers = [FieldAnswer(**a) for a in original["items"]]
            extras = [FieldAnswer(**a) for a in original["extra_fields"]]
            result = Extraction(
                sku, original["category_id"], tuple(answers), tuple(extras), original["review"]
            )
            result = replace(
                result,
                items=tuple(
                    normalize_answer(a, definitions.get(a.attribute)) for a in result.items
                ),
                extra_fields=tuple(
                    normalize_answer(a, definitions.get(a.attribute)) for a in result.extra_fields
                ),
            )
            result = validate_extraction(
                result, tuple(definitions.values()), card["text"], **validation_options
            )
            if category:
                result = complete_seller_fields(
                    result,
                    schema,
                    card["text"],
                    tuple(SellerParam(**p) for p in registry["cards"][sku]["seller_params"] or []),
                )
                result = validate_extraction(
                    result, tuple(definitions.values()), card["text"], **validation_options
                )
            results[sku] = result
            answer_rows.append({"sku_id": sku, "result": asdict(result)})
    cases = []
    for sku, card in registry["dev"].items():
        current = registry["cards"][sku]
        result = results[sku]
        gold: dict[str, list[Row]] = defaultdict(list)
        for row in registry["gold"][sku]:
            if row["attribute"] in targets[sku]:
                gold[row["attribute"]].append(row)
        for attribute, alternatives in gold.items():
            expected = {
                key(g["value"], g["unit"], profiles.get(attribute, {}), attribute)
                for g in alternatives
            }
            found = [
                asdict(a)
                for a in (*result.items, *result.extra_fields)
                if a.attribute == attribute and a.status == "supported"
            ]
            matched = any(
                key(
                    a["normalized_value"] if a["normalized_value"] is not None else a["value"],
                    a["normalized_unit"] if a["normalized_unit"] is not None else a["unit"],
                    profiles.get(attribute, {}),
                    attribute,
                )
                in expected
                for a in found
            )
            rejections = [asdict(r) for r in result.rejections if r.attribute == attribute]
            outcome = (
                "correct"
                if matched
                else "gold_disagreement"
                if found
                else "rejected"
                if rejections
                else "missing"
            )
            cases.append(
                {
                    "case_id": f"{sku}:{attribute}",
                    "sku_id": sku,
                    "attribute": attribute,
                    "selected_for_review": sku in selected,
                    "category_id": current["category_id"],
                    "category_correct": current["category_id"] == result.category_id,
                    "required_by_current_catalog": attribute
                    in required.get(current["category_id"], []),
                    "input_sha256": hashlib.sha256(card["text"].encode()).hexdigest(),
                    "gold": alternatives,
                    "answers": found,
                    "rejections": rejections,
                    "proposals": [a for a in proposals[sku] if a["attribute"] == attribute],
                    "outcome": outcome,
                    "legacy_diagnostics": diagnostic.get((sku, attribute), []),
                }
            )
    summary["dev_required_slots"] = len(cases)
    summary["review_slots"] = sum(r["selected_for_review"] for r in cases)
    if loaded_implementation() != loaded_before:
        raise ValueError("Implementation changed during preparation; use a frozen runtime")
    summary["implementation_sha256"] = loaded_before
    summary["protocol_sha256"] = digest(protocol_path)
    write_lines(output / "train-labels.jsonl", registry["train_annotations"])
    write_lines(output / "dev-cases.jsonl", cases)
    write_lines(output / "dev-results.jsonl", answer_rows)
    write_lines(
        output / "review-inputs.jsonl", (registry["cards"][sku] for sku in protocol["selected_ids"])
    )
    write_json(output / "source-audit.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("experiments", "data", "bundle", "protocol", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.experiments, args.data, args.bundle, args.protocol, args.output)


if __name__ == "__main__":
    main()
