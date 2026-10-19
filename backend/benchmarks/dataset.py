from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.card_text import SellerParam, build_card_text
from app.domain.profile import profile_attribute
from benchmarks.files import Row, identity, text_digest


def collect_cards(
    data: Path, seed: int
) -> tuple[list[Row], set[int], Counter[int], dict[str, int]]:
    splits = {r["sku_id"]: r["split"] for r in pq.read_table(data / "splits.parquet").to_pylist()}
    training = {sku for sku, split in splits.items() if split == "train"}
    hashes: set[str] = set()
    candidates: list[Row] = []
    counts: Counter[int] = Counter()
    sellers: Counter[str] = Counter()
    columns = ["sku_id", "category_id", "seller", "title", "description", "seller_params"]
    for batch in pq.ParquetFile(data / "cards.parquet").iter_batches(8192, columns=columns):
        for row in batch.to_pylist():
            split = splits.get(row["sku_id"])
            if split not in {"train", "test", "new_category"} or not row["title"]:
                continue
            text = build_card_text(
                row["title"],
                row["description"],
                tuple(SellerParam(**p) for p in row["seller_params"] or []),
            ).text
            signature = text_digest(text)
            if split == "train":
                hashes.add(signature)
                counts[row["category_id"]] += 1
                if row["seller"]:
                    sellers[row["seller"]] += 1
            else:
                candidates.append({**row, "split": split, "text_sha256": signature})
    eligible = []
    seen: set[str] = set()
    for row in sorted(candidates, key=lambda r: identity(seed, r["sku_id"])):
        signature = row["text_sha256"]
        if signature in hashes or signature in seen:
            continue
        seen.add(signature)
        eligible.append(row)
    return eligible, training, counts, dict(sellers)


def required_fields(data: Path) -> tuple[dict[int, list[str]], dict[str, float]]:
    fields: dict[int, list[str]] = defaultdict(list)
    weights: dict[str, float] = {}
    for row in sorted(
        pq.read_table(data / "required_attributes.parquet").to_pylist(),
        key=lambda r: (r["category_id"], r["rank"]),
    ):
        fields[row["category_id"]].append(row["attribute"])
        weights[f"{row['category_id']}:{row['attribute']}"] = row["weight"]
    return dict(fields), weights


def load_gold(data: Path, ids: set[int]) -> dict[int, list[Row]]:
    values: dict[int, list[Row]] = defaultdict(list)
    selected = pa.array(sorted(ids), type=pa.int64())
    for batch in pq.ParquetFile(data / "gold.parquet").iter_batches(100_000):
        kept = batch.filter(pc.is_in(batch.column("sku_id"), value_set=selected))
        for row in kept.to_pylist():
            if row["value"]:
                values[row["sku_id"]].append(row)
    return dict(values)


def choose_sample(
    candidates: list[Row],
    gold: dict[int, list[Row]],
    fields: dict[int, list[str]],
    counts: Counter[int],
    seed: int,
    test_each: int,
    new_each: int,
) -> list[Row]:
    buckets: dict[str, list[Row]] = defaultdict(list)
    for row in candidates:
        category = row["category_id"]
        expected = [
            g for g in gold.get(row["sku_id"], []) if g["attribute"] in fields.get(category, [])
        ]
        if not expected:
            continue
        group = (
            f"new:{category}"
            if row["split"] == "new_category"
            else "rare"
            if counts[category] < 100
            else "common"
        )
        buckets[group].append({**row, "gold": expected, "stratum": group})
    if not any(key.startswith("new:") for key in buckets):
        raise ValueError("No eligible new-category cards")
    result = []
    for group in ["common", "rare", *sorted(k for k in buckets if k.startswith("new:"))]:
        limit = new_each if group.startswith("new:") else test_each
        ranked = sorted(buckets[group], key=lambda r: identity(seed, r["sku_id"]))
        if len(ranked) < limit:
            raise ValueError(f"Not enough eligible cards in {group}: {len(ranked)} < {limit}")
        for row in ranked[:limit]:
            result.append(
                {**row, "population": len(ranked), "sampling_weight": len(ranked) / limit}
            )
    return sorted(result, key=lambda r: identity(seed, r["sku_id"]))


def catalog(
    data: Path,
    fields: dict[int, list[str]],
    training: set[int],
    seed: int,
) -> tuple[dict[int, CatalogCandidate], dict[str, Row], int]:
    category_ids = {
        r["sku_id"]: r["category_id"]
        for r in pq.read_table(
            data / "cards.parquet", columns=["sku_id", "category_id"]
        ).to_pylist()
        if r["sku_id"] in training
    }
    groups: dict[int, list[int]] = defaultdict(list)
    for sku, category in category_ids.items():
        groups[category].append(sku)
    profile_ids = {
        sku
        for ids in groups.values()
        for sku in sorted(ids, key=lambda sku: identity(seed, sku))[:20]
    }
    values = load_gold(data, profile_ids)
    global_values: dict[str, Counter[tuple[str, str | None]]] = defaultdict(Counter)
    category_values: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    for sku, records in values.items():
        category = category_ids[sku]
        for row in records:
            name = row["attribute"]
            if name not in fields.get(category, []):
                continue
            global_values[name][row["value"], row["unit"]] += 1
            category_values[category, name][row["value"]] += 1
    profiles = {name: profile_attribute(name, counts) for name, counts in global_values.items()}
    paths = {
        r["category_id"]: r["path"] for r in pq.read_table(data / "categories.parquet").to_pylist()
    }
    schemas = {}
    for category, names in fields.items():
        definitions = []
        for name in names:
            profile = profiles.get(name)
            definitions.append(
                CatalogField(
                    name,
                    str(profile.kind) if profile else "free",
                    profile.unit if profile else "",
                    tuple(v for v, _ in category_values[category, name].most_common(8)),
                )
            )
        schemas[category] = CatalogCandidate(category, paths[category], 0, tuple(definitions))
    return schemas, {name: asdict(profile) for name, profile in profiles.items()}, len(profile_ids)
