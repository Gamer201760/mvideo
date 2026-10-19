import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from app.domain.card_text import match_form
from app.domain.values import display_value
from benchmarks.files import Row, digest, read_lines, write_json, write_lines
from benchmarks.metrics import key


def raw_attributes(prediction: Row) -> set[str]:
    call = prediction["calls"][0]
    fields = json.loads(call["prompt"])["f"]
    return {
        fields[a["f"]] if type(a["f"]) is int else a["f"] for a in call["response"]["c"][0]["a"]
    }


def slot_audit(sample: list[Row], predictions: list[Row], profiles: Row) -> tuple[Row, list[Row]]:
    cards = {r["sku_id"]: r for r in sample}
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    rejections: dict[str, Counter[str]] = defaultdict(Counter)
    details: list[Row] = []
    for prediction in predictions:
        mode = prediction["mode"]
        row = cards[prediction["sku_id"]]
        result = prediction["result"]
        extraction = result["extraction"]
        answers: dict[str, list[Row]] = defaultdict(list)
        expected: dict[str, list[Row]] = defaultdict(list)
        for gold in row["gold"]:
            expected[gold["attribute"]].append(gold)
        for answer in [*extraction["items"], *extraction["extra_fields"]]:
            if answer["status"] == "supported":
                answers[answer["attribute"]].append(answer)
        rejected = {r["attribute"] for r in extraction["rejections"]}
        rejections[mode].update(r["reason"] for r in extraction["rejections"])
        declared = raw_attributes(prediction)
        schema = {f["attribute"] for f in (result.get("category") or {}).get("fields", [])}
        if row["split"] == "test":
            counts[mode]["test_cards_wrong_category"] += (
                extraction["category_id"] != row["category_id"]
            )
        for attribute, alternatives in expected.items():
            profile = profiles.get(attribute, {})
            gold_keys = {key(g["value"], g["unit"], profile, attribute) for g in alternatives}
            found = answers[attribute]
            actual = {
                key(
                    a["normalized_value"] if a.get("normalized_value") is not None else a["value"],
                    a["normalized_unit"] if a.get("normalized_unit") is not None else a["unit"],
                    profile,
                    attribute,
                )
                for a in found
            }
            correct = bool(gold_keys & actual)
            if correct:
                reason = "correct"
            elif found:
                reason = "filled_gold_disagrees"
            elif attribute in rejected:
                reason = "missing_rejected"
            elif attribute not in schema and attribute not in declared:
                reason = "missing_outside_selected_schema"
            elif attribute not in declared:
                reason = "missing_model_omission"
            else:
                reason = "missing_parser_or_completion"
            counts[mode][reason] += 1
            literal = any(
                re.search(
                    rf"(?<!\w){re.escape(match_form(display_value(g['value'], g['unit'])))}(?!\w)",
                    match_form(result["text"]),
                )
                for g in alternatives
            )
            if not correct:
                counts[mode]["failed_literal_found" if literal else "failed_literal_not_found"] += 1
            if (
                found
                and not correct
                and any(key(a["value"], a["unit"], profile, attribute) in gold_keys for a in found)
            ):
                counts[mode]["normalization_lost_gold_match"] += 1
            details.append(
                {
                    "mode": mode,
                    "sku_id": row["sku_id"],
                    "attribute": attribute,
                    "reason": reason,
                    "gold_literal_found": literal,
                }
            )
    return {
        mode: {"slots": dict(counts[mode]), "rejections_all_fields": dict(rejections[mode])}
        for mode in counts
    }, details


def compare(bundle: Path, before: Path, after: Path, dev_before: Path, dev_after: Path) -> Row:
    old = json.loads((before / "report.json").read_text())
    new = json.loads((after / "report.json").read_text())
    for name in ("protocol_sha256", "results_sha256"):
        if old[name] != new[name]:
            raise ValueError(f"Before/after input mismatch: {name}")
    if not old["requests_equal"] or not new["requests_equal"]:
        raise ValueError("Replay changed a model request")
    dev_old = json.loads((dev_before / "report.json").read_text())
    dev_new = json.loads((dev_after / "report.json").read_text())
    if dev_old["sources_sha256"] != dev_new["sources_sha256"]:
        raise ValueError("Development inputs changed")
    changes: Counter[str] = Counter()
    for left, right in zip(
        read_lines(dev_before / "answers.jsonl"),
        read_lines(dev_after / "answers.jsonl"),
        strict=True,
    ):
        if left["sku_id"] != right["sku_id"] or left["answer"] != right["answer"]:
            raise ValueError("Development answer ordering/content changed")
        if left["error"] != right["error"]:
            changes[f"{left['error']} -> {right['error'] or 'accepted'}"] += 1
    sample = read_lines(bundle / "sample.jsonl")
    profiles = json.loads((bundle / "profiles.json").read_text())
    audits = {}
    for label, directory in (("before", before), ("after", after)):
        audits[label], details = slot_audit(
            sample, read_lines(directory / "predictions.jsonl"), profiles
        )
        write_lines(directory / "slot-audit.jsonl", details)
    return {
        "version": "quality-error-analysis-v2",
        "scope": "Same saved answers, inputs and v1.1 scorer; no fresh model calls or latency claim",
        "new_model_calls": 0,
        "protocol_sha256": old["protocol_sha256"],
        "saved_response_set_sha256": hashlib.sha256(
            json.dumps(old["results_sha256"], sort_keys=True).encode()
        ).hexdigest(),
        "scorer_sha256": {n: digest(Path(__file__).parent / n) for n in ("metrics.py", "score.py")},
        "implementation_before": old["implementation_sha256"],
        "implementation_after": new["implementation_sha256"],
        "development": {"before": dev_old, "after": dev_new, "transitions": dict(changes)},
        "results": {
            mode: {
                label: {
                    k: reports["results"][mode][k]
                    for k in (
                        "normalized",
                        "raw_exact",
                        "inverse_sampling_weighted",
                        "catalog_metadata_weighted",
                        "slices",
                        "rejected_values",
                        "cards_with_invalid_quote_offsets",
                    )
                }
                for label, reports in (("before", old), ("after", new))
            }
            for mode in old["results"]
        },
        "slot_diagnostics": audits,
        "diagnostic_limits": [
            "Partitions describe pipeline outcomes, not exclusive semantic root causes",
            "Literal absence is not proof of unavailable gold; unit conversion and paraphrase remain",
            "Literal presence does not establish the correct object, field or variant",
            "Wrong-category counts cover test only; new-category proposals lack semantic labels",
            "Gold disagreements need manual adjudication; gold and scorer are unchanged",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("bundle", "before", "after", "dev-before", "dev-after", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    write_json(
        args.output, compare(args.bundle, args.before, args.after, args.dev_before, args.dev_after)
    )


if __name__ == "__main__":
    main()
