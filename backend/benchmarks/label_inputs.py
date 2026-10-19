import json
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.domain.card_text import SellerParam, build_card_text
from benchmarks.dataset import load_gold
from benchmarks.files import Row, digest, read_lines, text_digest


def processed_cards(data: Path, ids: set[int]) -> dict[int, Row]:
    selected = pa.array(sorted(ids), type=pa.int64())
    rows = {}
    for batch in pq.ParquetFile(data / "cards.parquet").iter_batches(8192):
        kept = batch.filter(pc.is_in(batch.column("sku_id"), value_set=selected))
        for row in kept.to_pylist():
            row["text"] = build_card_text(
                row["title"],
                row["description"],
                tuple(SellerParam(**p) for p in row["seller_params"] or []),
            ).text
            rows[row["sku_id"]] = row
    return rows


def gold_targets(rows: list[Row], attribute: str) -> set[tuple[str, str | None]]:
    return {(r["value"], r["unit"]) for r in rows if r["attribute"] == attribute}


def align_sources(experiments: Path, data: Path, bundle: Path) -> tuple[Row, Row]:
    protocol = json.loads((bundle / "protocol.json").read_text())
    for name, expected in protocol["artifacts_sha256"].items():
        if digest(bundle / name) != expected:
            raise ValueError(f"Frozen benchmark artifact changed: {name}")
    for name, expected in protocol["source_sha256"].items():
        if digest(data / name) != expected:
            raise ValueError(f"Processed source changed: {name}")
    root = experiments / "gliner-01"
    pool = {r["sku_id"]: r for r in read_lines(root / "train_pool.jsonl")}
    annotation_paths = sorted((root / "annotations-clean-pilot/batches").glob("*.json"))
    annotations = [r for p in annotation_paths for r in json.loads(p.read_text())["items"]]
    if len({(r["sku_id"], r["attribute"]) for r in annotations}) != len(annotations):
        raise ValueError("Duplicate source annotation pair")
    dev_root = experiments / "attribute-flow-compact-main-01"
    dev = {r["sku_id"]: r for r in json.loads((dev_root / "cards.json").read_text())}
    ids = {r["sku_id"] for r in annotations} | set(dev)
    current = processed_cards(data, ids)
    gold = load_gold(data, ids)
    splits = {r["sku_id"]: r["split"] for r in pq.read_table(data / "splits.parquet").to_pylist()}
    if any(splits.get(sku) != "val" for sku in dev):
        raise ValueError("Development is not val-only")
    if any(splits.get(r["sku_id"]) != "train" for r in annotations):
        raise ValueError("Historical annotations are not train-only")
    if any(current[sku]["text"] != row["text"] for sku, row in dev.items()):
        raise ValueError("Historical dev text differs from current input")
    control = read_lines(bundle / "sample.jsonl")
    control_ids = {r["sku_id"] for r in control}
    control_texts = {
        text_digest(
            build_card_text(
                r["title"],
                r["description"],
                tuple(SellerParam(**p) for p in r["seller_params"] or []),
            ).text
        )
        for r in control
    }
    if ids & control_ids or any(text_digest(current[sku]["text"]) in control_texts for sku in ids):
        raise ValueError("Source audit overlaps benchmark control")
    aligned = []
    for row in annotations:
        sku, attribute = row["sku_id"], row["attribute"]
        text = current[sku]["text"]
        context_ok = bool(row["context"]) and row["context"] in text
        span_ok = (
            row["status"] != "supported"
            or bool(row["spans"])
            and all(bool(span) and span in text for span in row["spans"])
        )
        target_ok = gold_targets(pool[sku]["gold"], attribute) == gold_targets(gold[sku], attribute)
        binding_ok = pool[sku]["text"] == text and target_ok
        eligible = binding_ok and (row["status"] != "supported" or context_ok and span_ok)
        aligned.append(
            {
                **row,
                "input_sha256": text_digest(text),
                "reuse_eligible": eligible,
                "context_matches": context_ok,
                "spans_match": span_ok,
                "gold_target_matches": target_ok,
                "input_target_matches": binding_ok,
            }
        )
    diagnostics_path = experiments / "e5-error-cases-01/diagnostic_val_errors.jsonl"
    diagnostics = []
    for row in read_lines(diagnostics_path):
        sku = row["sku_id"]
        if sku not in dev:
            continue
        evidence = row.get("gold_evidence")
        evidence_ok = (
            evidence is not None
            and current[sku]["text"][evidence["start"] : evidence["end"]] == evidence["evidence"]
        )
        diagnostics.append(
            {
                **row,
                "input_matches": row["text"] == current[sku]["text"],
                "evidence_offsets_match": evidence_ok,
            }
        )
    sources = [
        root / "train_pool.jsonl",
        dev_root / "cards.json",
        diagnostics_path,
        *annotation_paths,
    ]
    registry: Row = {
        "train_annotations": aligned,
        "diagnostics": diagnostics,
        "cards": current,
        "dev": dev,
        "gold": gold,
    }
    summary: Row = {
        "source_sha256": {str(p.relative_to(experiments)): digest(p) for p in sources},
        "processed_sha256": protocol["source_sha256"],
        "bundle_artifacts_sha256": protocol["artifacts_sha256"],
        "train_annotations": len(aligned),
        "train_cards": len({r["sku_id"] for r in aligned}),
        "train_statuses": dict(Counter(r["status"] for r in aligned)),
        "train_reuse_eligible": sum(r["reuse_eligible"] for r in aligned),
        "train_human_verified": sum(r["human_verified"] for r in aligned),
        "train_labels_reusable_for_val_by_sku": len({r["sku_id"] for r in aligned} & set(dev)),
        "dev_cards_current_text_exact": len(dev),
        "dev_diagnostic_rows": len(diagnostics),
        "dev_diagnostic_cards": len({r["sku_id"] for r in diagnostics}),
        "dev_diagnostic_text_exact": sum(r["input_matches"] for r in diagnostics),
        "dev_diagnostic_exact_evidence": sum(r["evidence_offsets_match"] for r in diagnostics),
        "control_id_and_exact_text_overlap": 0,
        "near_duplicates": "Not audited; no claim of historical independence",
    }
    return registry, summary


def diagnostics_by_pair(registry: Row) -> dict[tuple[int, str], list[Row]]:
    result: dict[tuple[int, str], list[Row]] = defaultdict(list)
    for row in registry["diagnostics"]:
        result[row["sku_id"], row["attribute"]].append(row)
    return result
