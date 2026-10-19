import argparse
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from benchmarks.dataset import catalog, choose_sample, collect_cards, load_gold, required_fields
from benchmarks.files import SOURCE_NAMES, digest, implementation, write_json, write_lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261019)
    parser.add_argument("--test-each", type=int, default=40)
    parser.add_argument("--new-each", type=int, default=5)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; use a new directory to preserve the fixed sample")
    if min(args.test_each, args.new_each) < 1:
        parser.error("Sample sizes must be positive")
    for name in SOURCE_NAMES:
        if not (args.data / name).is_file():
            parser.error(f"Missing processed source: {args.data / name}")
    print("Reading cards and excluding exact normalized train duplicates", flush=True)
    fields, weights = required_fields(args.data)
    candidates, training, counts, sellers = collect_cards(args.data, args.seed)
    print(f"Eligible deduplicated candidates: {len(candidates)}", flush=True)
    gold = load_gold(args.data, {r["sku_id"] for r in candidates})
    sample = choose_sample(
        candidates, gold, fields, counts, args.seed, args.test_each, args.new_each
    )
    print("Building profiles and value vocabularies from train only", flush=True)
    schemas, profiles, profile_cards = catalog(args.data, fields, training, args.seed)
    withheld = sorted({row["category_id"] for row in sample if row["split"] == "new_category"})
    for row in sample:
        row["category_path"] = schemas[row["category_id"]].path
        row["train_category_cards"] = counts[row["category_id"]]
        row["train_seller_cards"] = sellers.get(row["seller"], 0)
    args.output.mkdir(parents=True)
    write_lines(args.output / "sample.jsonl", sample)
    write_json(args.output / "catalog.json", [asdict(c) for c in schemas.values()])
    write_json(args.output / "profiles.json", profiles)
    write_json(args.output / "weights.json", weights)
    protocol = {
        "version": "release-benchmark-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "seed": args.seed,
        "sample_size": len(sample),
        "strata": dict(Counter(row["stratum"] for row in sample)),
        "source_sha256": {name: digest(args.data / name) for name in SOURCE_NAMES},
        "artifacts_sha256": {
            name: digest(args.output / name)
            for name in ("sample.jsonl", "catalog.json", "profiles.json", "weights.json")
        },
        "implementation_sha256": implementation(),
        "model_label": "gigachat (user-provided configuration name)",
        "requested_model": "default",
        "modes": ["rules", "model", "hybrid"],
        "concurrency": 2,
        "timeout_s": 120,
        "retries": 0,
        "catalog_categories": len(schemas),
        "profile_train_cards": profile_cards,
        "withheld_category_ids": withheld,
        "population": "Existing test/new_category split; nonempty title and required gold",
        "sampling": "SHA256(seed:sku_id); 40 test/category train size <100, 40 >=100; 5 per new category",
        "leakage_controls": [
            "Evaluation SKU IDs and normalized full texts are distinct from train",
            "Evaluation full texts are mutually distinct; no near-duplicate guarantee",
            "Profiles and category value vocabularies use at most 20 train SKUs per category",
            "Evaluation category, gold and seller identity are not sent to the model",
            "All new_category schemas are withheld from retrieval and prompts",
            "No training products or retrieval examples; same schema-only RAG as the release",
            "Per-card isolation: no feedback, saved corrections or learned categories",
        ],
        "schema_caveat": "Existing required-field definitions/weights are treated as fixed catalog metadata; their upstream construction is not claimed train-only",
        "test_caveat": "Existing splits were evaluated by earlier project versions; no claim of historically untouched test data",
        "scope": "Current extraction/validation use cases on imported real schemas, not the shipped 8-category demo configuration",
        "metrics": [
            "Required-gold-slot normalized precision/recall/F1; wrong values count FP+FN",
            "Raw exact match alongside deterministic normalized match; gold alternatives deduplicated",
            "Predictions outside required gold slots reported separately, not scored as hallucinations",
            "Micro, per-attribute/category/seller and split/rarity slices; category top1/top3",
            "Inverse-sampling and metadata-weighted scores are separate from sample micro scores",
            "Failures count as empty predictions; no survivor-only quality metrics",
            "Deterministic paired card bootstrap 1000 repeats for hybrid minus rules F1",
            "Latency p50/p95, model-call share, recorded tokens; USD unknown without tariffs",
        ],
    }
    write_json(args.output / "protocol.json", protocol)
    print(
        f"Frozen {len(sample)} cards, {len(schemas)} schemas, withheld {len(withheld)} categories",
        flush=True,
    )


if __name__ == "__main__":
    main()
