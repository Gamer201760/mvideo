import argparse
import json
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from app.domain.card_text import SellerParam, build_card_text
from benchmarks.acceptance_duplicates import DuplicateIndex
from benchmarks.files import (
    Row,
    digest,
    identity,
    implementation,
    read_lines,
    write_json,
    write_lines,
)


def card_text(row: Row) -> str:
    return build_card_text(
        row["title"],
        row["description"],
        tuple(SellerParam(**p) for p in row["seller_params"] or []),
    ).text


def historical_ids(paths: list[Path]) -> set[int]:
    result: set[int] = set()
    for path in paths:
        with path.open() as stream:
            for line in stream:
                result.update(int(m[1]) for m in re.finditer(r'"sku_id"\s*:\s*(\d+)', line))
    return result


def prepare(
    data: Path, bundle: Path, history: list[Path], output: Path, seed: int, pool: int
) -> None:
    if output.exists():
        raise ValueError("Output exists; preserve frozen studies")
    sources = {str(path.resolve()): digest(path) for path in history}
    data_sources = {name: digest(data / name) for name in ["cards.parquet", "splits.parquet"]}
    catalog_sha256 = digest(bundle / "catalog.json")
    used = historical_ids(history)
    used.update(r["sku_id"] for r in read_lines(bundle / "sample.jsonl"))
    splits = {r["sku_id"]: r["split"] for r in pq.read_table(data / "splits.parquet").to_pylist()}
    categories = {r["category_id"] for r in json.loads((bundle / "catalog.json").read_text())}
    ids = sorted(
        (sku for sku, split in splits.items() if split == "val" and sku not in used),
        key=lambda sku: identity(seed, sku),
    )
    selected = set(ids[:pool])
    candidates: list[Row] = []
    columns = ["sku_id", "category_id", "title", "description", "seller_params"]
    for batch in pq.ParquetFile(data / "cards.parquet").iter_batches(4096, columns=columns):
        candidates.extend(
            row
            for row in batch.to_pylist()
            if row["sku_id"] in selected and row["title"] and row["category_id"] in categories
        )
    candidates.sort(key=lambda row: identity(seed, row["sku_id"]))
    index = DuplicateIndex(card_text(row) for row in candidates)
    excluded = set()
    checked = 0
    for batch in pq.ParquetFile(data / "cards.parquet").iter_batches(4096, columns=columns):
        for row in batch.to_pylist():
            if splits.get(row["sku_id"]) == "train" or row["sku_id"] in used:
                excluded.update(index.matches(card_text(row)))
                checked += 1
        if checked and checked % 20000 < 4096:
            print(
                f"Reference cards checked: {checked}; excluded pool cards: {len(excluded)}",
                flush=True,
            )
    retained: list[tuple[int, Row]] = []
    for i, row in enumerate(candidates):
        if i in excluded:
            continue
        if index.matches(card_text(row)) & {j for j, _ in retained}:
            continue
        retained.append((i, row))
    if len(retained) < 130:
        raise ValueError(f"Insufficient duplicate-filtered cards: {len(retained)} <130")
    sample = []
    for i, (_, row) in enumerate(retained[:130]):
        sample.append(
            {
                **row,
                "card_id": f"C{i + 1:04}",
                "partition": "tune" if i < 30 else "confirm",
                "text": card_text(row),
            }
        )
    if any(digest(Path(name)) != sha for name, sha in sources.items()):
        raise ValueError("Historical artifacts changed during selection")
    if (
        any(digest(data / name) != sha for name, sha in data_sources.items())
        or digest(bundle / "catalog.json") != catalog_sha256
    ):
        raise ValueError("Processed cards, splits or catalog changed during selection")
    write_lines(output / "sample.jsonl", sample)
    protocol = {
        "version": "acceptance-study-v1",
        "seed": seed,
        "input_cards": 130,
        "partition_cards": {"tune": 30, "confirm": 100},
        "selection": "SHA256(seed:sku_id), val IDs absent from inventoried histories; no gold or prediction filtering",
        "population": "First fixed random hash-ranked pool of unseen val IDs with catalog schemas; lexical duplicates removed before inference",
        "history_sha256": sources,
        "source_sha256": data_sources,
        "catalog_sha256": catalog_sha256,
        "sample_sha256": digest(output / "sample.jsonl"),
        "selection_implementation_sha256": implementation(),
        "inventory": {
            "historical_ids": len(used),
            "pool_requested": pool,
            "pool_loaded": len(candidates),
            "reference_cards": checked,
            "excluded_near_reference": len(excluded),
            "retained": len(retained),
        },
        "duplicate_rule": "Normalized word-trigram Jaccard>=0.8; exact prefix-filter search against train/historical cards and mutual selected cards; not semantic deduplication",
        "engine": "Current hybrid orchestration with LocalRulesModel, full imported schema catalog, category_id=None, no persisted feedback or proxy risk model",
        "review": "Two independent agents, full input/category/final values; blinded to score, acceptance, gold, partition and each other; disagreements/unknown remain unconfirmed",
        "policy": {"threshold": 0.95, "enabled": True, "target": 0.95, "alpha": 0.05},
        "selection_policy": "Validate fixed acceptance gate; heuristic admissible scores are all1, no threshold tuning on confirm",
        "primary": "Among cards with >=1 autoaccepted field, both reviewers confirm category and all accepted final values; one-sided exact binomial95 lower>=0.95",
        "secondary": [
            "all-accepted-field agent agreement precision",
            "accepted fields / all supported fields",
            "cards with acceptance / all input cards",
            "disagreements and unknown count as unconfirmed",
        ],
        "stop_rule": "Exactly130 input cards, no expansion after reviews; no certified threshold if gate fails; any runtime change consumes confirm as development",
        "limitations": [
            "Agent consensus is not human gold",
            "Historical inventory is bounded to declared artifacts; unknown external usage cannot be excluded",
            "Exact binomial interval assumes independent card outcomes and does not account for annotation errors or lexical cluster dependence",
            "LocalRulesModel validation does not measure external gateway inference",
        ],
        "sample_categories": dict(Counter(str(row["category_id"]) for row in sample)),
    }
    write_json(output / "protocol.json", protocol)
    print(json.dumps(protocol["inventory"]), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("data", "bundle", "history-list", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026101903)
    parser.add_argument("--pool", type=int, default=1000)
    args = parser.parse_args()
    paths = [Path(line) for line in args.history_list.read_text().splitlines() if line.strip()]
    if not paths or not all(path.is_file() for path in paths):
        raise ValueError("Historical inventory must contain existing source paths")
    prepare(args.data, args.bundle, paths, args.output, args.seed, args.pool)


if __name__ == "__main__":
    main()
