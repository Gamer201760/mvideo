import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from benchmarks.files import Row, digest, read_lines, text_digest, write_json, write_lines
from benchmarks.metrics import Counts, evaluate, paired_bootstrap, quantile


def aggregate(
    sample: list[Row], predictions: dict[int, Row], profiles: dict[str, Row], weights: Row
) -> Row:
    total, exact, population, traffic = Counts(), Counts(), Counts(), Counts()
    slices: dict[str, Counts] = defaultdict(Counts)
    attributes: dict[str, Counts] = defaultdict(Counts)
    categories: dict[str, Counts] = defaultdict(Counts)
    sellers: dict[str, Counts] = defaultdict(Counts)
    failures = category_correct = retrieved = unscored = quote_errors = rejections = 0
    latencies, successful_latencies = [], []
    tokens = {"input_tokens": 0, "output_tokens": 0}
    missing_usage = 0
    calls = 0
    models: set[str] = set()
    for row in sample:
        prediction = predictions[row["sku_id"]]
        counts, per_attribute, extra = evaluate(row, prediction, profiles)
        raw, _, _ = evaluate(row, prediction, profiles, raw=True)
        total.add(counts)
        exact.add(raw)
        population.add(counts, row["sampling_weight"])
        unscored += extra
        for name, counts_for_attribute in per_attribute.items():
            attributes[name].add(counts_for_attribute)
            traffic.add(
                counts_for_attribute,
                row["sampling_weight"] * weights.get(f"{row['category_id']}:{name}", 1),
            )
        categories[str(row["category_id"])].add(counts)
        seller_id = f"seller:{text_digest(row['seller'])[:12]}" if row["seller"] else "unknown"
        sellers[seller_id].add(counts)
        for name in (
            row["split"],
            row["stratum"],
            "seller_seen" if row["train_seller_cards"] else "seller_unseen",
        ):
            slices[name].add(counts)
        failed = "error" in prediction
        failures += failed
        latencies.append(prediction["wall_ms"])
        if not failed:
            successful_latencies.append(prediction["wall_ms"])
        predicted_category = prediction.get("result", {}).get("category")
        category_correct += bool(
            predicted_category and predicted_category["category_id"] == row["category_id"]
        )
        retrieved += row["category_id"] in prediction.get("retrieved_category_ids", [])
        quote_errors += prediction.get("evidence_exact") is False
        rejections += len(prediction.get("result", {}).get("extraction", {}).get("rejections", []))
        for call in prediction["calls"]:
            usage = call.get("usage", {})
            if usage.get("model") == "local_rules":
                continue
            calls += 1
            if usage.get("model"):
                models.add(usage["model"])
            for name in tokens:
                if usage.get(name) is None:
                    missing_usage += 1
                else:
                    tokens[name] += usage[name]
    known = [r for r in sample if r["split"] == "test"]
    new = [r for r in sample if r["split"] == "new_category"]
    proposed = sum(
        bool(
            predictions[r["sku_id"]]
            .get("result", {})
            .get("extraction", {})
            .get("proposed_category")
        )
        for r in new
    )
    return {
        "cards": len(sample),
        "failed_cards": failures,
        "normalized": total.metrics(),
        "raw_exact": exact.metrics(),
        "inverse_sampling_weighted": population.metrics(),
        "catalog_metadata_weighted": traffic.metrics(),
        "slices": {name: value.metrics() for name, value in sorted(slices.items())},
        "per_attribute": {name: value.metrics() for name, value in sorted(attributes.items())},
        "per_category": {name: value.metrics() for name, value in sorted(categories.items())},
        "per_seller": {name: value.metrics() for name, value in sorted(sellers.items())},
        "category_top1_test": category_correct / len(known) if known else None,
        "category_recall_top3_test": retrieved / len(known) if known else None,
        "new_category_proposal_rate": proposed / len(new) if new else None,
        "new_category_correctness": "Not semantically labelled; proposal rate is not accuracy",
        "unscored_predicted_values": unscored,
        "cards_with_invalid_quote_offsets": quote_errors,
        "rejected_values": rejections,
        "latency_ms": {
            "p50": quantile(latencies, 0.5),
            "p95": quantile(latencies, 0.95),
            "successful_p50": quantile(successful_latencies, 0.5),
            "successful_p95": quantile(successful_latencies, 0.95),
        },
        "model_calls": calls,
        "calls_per_card": calls / len(sample),
        "reported_models": sorted(models),
        "recorded_tokens": tokens,
        "missing_token_counters": missing_usage,
        "cost_usd": None,
        "cost_note": "Gateway tariffs/cost were not returned; no monetary estimate is invented",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads((args.bundle / "protocol.json").read_text())
    for name, expected in protocol["artifacts_sha256"].items():
        if digest(args.bundle / name) != expected:
            parser.error(f"Frozen artifact changed: {name}")
    sample = read_lines(args.bundle / "sample.jsonl")
    profiles = json.loads((args.bundle / "profiles.json").read_text())
    weights = json.loads((args.bundle / "weights.json").read_text())
    predictions: dict[str, dict[int, Row]] = {}
    for mode in protocol["modes"]:
        predictions[mode] = {}
        for row in sample:
            path = args.bundle / "results" / f"{mode}-{row['sku_id']}.json"
            if not path.exists():
                parser.error(f"Missing prediction: {path}; do not score an incomplete run")
            prediction = json.loads(path.read_text())
            if prediction["sku_id"] != row["sku_id"] or prediction["mode"] != mode:
                parser.error(f"Prediction identity mismatch: {path}")
            predictions[mode][row["sku_id"]] = prediction
    bootstrap_rows = []
    for row in sample:
        bootstrap_rows.append(
            {
                "stratum": row["stratum"],
                **{
                    mode: evaluate(row, predictions[mode][row["sku_id"]], profiles)[0].metrics()
                    for mode in ("rules", "hybrid")
                },
            }
        )
    for row in bootstrap_rows:
        for mode in ("rules", "hybrid"):
            row[mode] = {key: row[mode][key] for key in ("tp", "fp", "fn", "filled", "slots")}
    results = {
        mode: aggregate(sample, rows, profiles, weights) for mode, rows in predictions.items()
    }
    secondary_rows = [
        {
            "stratum": row["stratum"],
            "rules": evaluate(row, predictions["model"][row["sku_id"]], profiles)[0].metrics(),
            "hybrid": evaluate(row, predictions["hybrid"][row["sku_id"]], profiles)[0].metrics(),
        }
        for row in sample
    ]
    for row in secondary_rows:
        for mode in ("rules", "hybrid"):
            row[mode] = {key: row[mode][key] for key in ("tp", "fp", "fn", "filled", "slots")}
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "evaluation_revision": "v1.1-preserve-units-without-numeric-profile",
        "scorer_sha256": {
            name: digest(Path(__file__).parent / name)
            for name in ("metrics.py", "score.py", "files.py")
        },
        "protocol": protocol,
        "protocol_sha256": digest(args.bundle / "protocol.json"),
        "run_status": json.loads((args.bundle / "run-status.json").read_text()),
        "provenance": {
            name: json.loads((args.bundle / name).read_text())
            for name in ("source-audit.json", "input-audit.json", "implementation/version.json")
            if (args.bundle / name).is_file()
        },
        "results": results,
        "hybrid_minus_rules": {
            "delta_f1": results["hybrid"]["normalized"]["f1"]
            - results["rules"]["normalized"]["f1"],
            **paired_bootstrap(bootstrap_rows, protocol["seed"]),
        },
        "exploratory_hybrid_minus_model": {
            "delta_f1": results["hybrid"]["normalized"]["f1"]
            - results["model"]["normalized"]["f1"],
            "status": "Secondary exploratory interval; not predeclared as the primary comparison",
            **paired_bootstrap(secondary_rows, protocol["seed"]),
        },
    }
    write_json(args.output, report)
    write_lines(
        args.bundle / "predictions.jsonl",
        (
            {
                "sku_id": sku,
                "mode": mode,
                "error": prediction.get("error"),
                "result": prediction.get("result"),
                "wall_ms": prediction["wall_ms"],
            }
            for mode, rows in predictions.items()
            for sku, prediction in rows.items()
        ),
    )
    print(json.dumps({mode: r["normalized"] for mode, r in results.items()}, indent=2))


if __name__ == "__main__":
    main()
