import argparse
import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from app.domain.attribute_flow import CatalogField, FieldAnswer
from app.domain.card_text import SellerParam, build_card_text
from app.domain.evidence_validation import evidence_error
from app.domain.split import split_of
from benchmarks.files import Row, digest, read_lines, text_digest, write_json, write_lines


def audit(experiment: Path, data: Path, bundle: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Output exists; choose a new directory")
    protocol = json.loads((bundle / "protocol.json").read_text())
    for name, expected in protocol["source_sha256"].items():
        if digest(data / name) != expected:
            raise ValueError(f"Processed source differs from benchmark: {name}")
    splits = {r["sku_id"]: r["split"] for r in pq.read_table(data / "splits.parquet").to_pylist()}
    historical = json.loads((experiment / "protocol.json").read_text())
    cards = json.loads((experiment / "cards.json").read_text())
    by_id = {r["sku_id"]: r for r in cards}
    if set(historical["evaluation_ids"]) != set(by_id):
        raise ValueError("Historical evaluation IDs differ from saved cards")
    if any(splits.get(sku) != "val" for sku in by_id):
        raise ValueError("Development requires val-only cards")
    if any(splits.get(sku) != "train" for sku in historical["train_ids"]):
        raise ValueError("Historical examples must originate from train")
    sample = read_lines(bundle / "sample.jsonl")
    control_ids = {r["sku_id"] for r in sample}
    control_texts = {
        text_digest(
            build_card_text(
                r["title"],
                r["description"],
                tuple(SellerParam(**p) for p in r["seller_params"] or []),
            ).text
        )
        for r in sample
    }
    overlap_ids = len(set(by_id) & control_ids)
    overlap_texts = sum(text_digest(r["text"]) in control_texts for r in cards)
    if overlap_ids or overlap_texts:
        raise ValueError("Development overlaps the fixed control")
    rows: list[Row] = []
    sources = [experiment / "protocol.json", experiment / "cards.json"]
    for path in sorted((experiment / "batches").glob("*.json")):
        sources.append(path)
        for result in json.loads(path.read_text())["initial"]:
            card = by_id[result["sku_id"]]
            category = next(
                (c for c in card["candidates"] if c["category_id"] == result["category_id"]), None
            )
            for answer in [*result["items"], *result["extra_fields"]]:
                if answer["status"] != "supported":
                    continue
                field = (
                    next(
                        (f for f in category["fields"] if f["attribute"] == answer["attribute"]),
                        None,
                    )
                    if category
                    else None
                )
                error = evidence_error(
                    FieldAnswer(**answer), CatalogField(**field) if field else None, card["text"]
                )
                rows.append({"sku_id": card["sku_id"], "answer": answer, "error": error})
    write_lines(output / "answers.jsonl", rows)
    write_json(
        output / "report.json",
        {
            "scope": "Revalidation of historical initial answers, not fresh model extraction or F1",
            "cards": len(cards),
            "answers": len(rows),
            "outcomes": dict(Counter(r["error"] or "accepted" for r in rows)),
            "split_audit": {
                "dev_splits": dict(Counter(splits[sku] for sku in by_id)),
                "historical_train_ids": len(historical["train_ids"]),
                "control_id_overlap": overlap_ids,
                "control_exact_text_overlap": overlap_texts,
                "nonwithheld_split_hash_mismatches": sum(
                    split != "new_category" and split != split_of(sku, 42, 0.1, 0.1)
                    for sku, split in splits.items()
                ),
                "near_duplicates": "Not audited; val was used by previous experiments",
            },
            "sources_sha256": {str(p.relative_to(experiment)): digest(p) for p in sources},
            "processed_sha256": protocol["source_sha256"],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.experiment, args.data, args.bundle, args.output)


if __name__ == "__main__":
    main()
