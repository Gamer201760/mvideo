import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.prepare_data import digest

type Row = dict[str, Any]


def verify_inputs(raw: Path, processed: Path) -> Row:
    manifest_path = processed / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing {manifest_path}; run python -m app.prepare_data first")
    manifest: Row = json.loads(manifest_path.read_text())
    for group, root in (("sources", raw), ("outputs", processed)):
        for name, expected in manifest[group].items():
            if not (root / name).is_file() or digest(root / name) != expected["sha256"]:
                raise ValueError(f"Dataset checksum mismatch: {root / name}")
    return manifest


def input_table(raw: Path) -> list[Row]:
    return [
        {
            "файл": path.name,
            "строк": pq.ParquetFile(path).metadata.num_rows if path.suffix == ".parquet" else None,
            "MiB": round(path.stat().st_size / 1024**2, 1),
        }
        for path in (raw / "sku_desc.parquet", raw / "query_clicks.parquet", raw / "skus.pkl")
    ]


def text_quality(raw: Path) -> Row:
    counts: Counter[str] = Counter()
    lengths: dict[str, list[Any]] = {"title": [], "description": []}
    source = pq.ParquetFile(raw / "sku_desc.parquet")
    for batch in source.iter_batches(8192, columns=["title", "description"]):
        for name, parts in lengths.items():
            values = pc.fill_null(batch.column(name), "")
            size = pc.utf8_length(values)
            parts.append(size.to_numpy(zero_copy_only=False))
            counts[f"пустой {name}"] += int(
                pc.sum(pc.cast(pc.equal(size, 0), pa.int64())).as_py() or 0
            )
        body = pc.fill_null(batch.column("description"), "")
        for name, pattern in (
            ("HTML в описании", r"<\s*/?\s*(br|p|li|ul|b|div)\b"),
            ("блок характеристик", r"(?i)характеристик[а-яё]*\s*:"),
        ):
            hits = pc.match_substring_regex(body, pattern)
            counts[name] += int(pc.sum(pc.cast(hits, pa.int64())).as_py() or 0)
    result: Row = {
        "cards": source.metadata.num_rows,
        "quality": [
            {"признак": name, "карточек": value, "%": 100 * value / source.metadata.num_rows}
            for name, value in counts.items()
        ],
        "lengths": {},
    }
    for name, parts in lengths.items():
        values = np.concatenate(parts)
        histogram, bins = np.histogram(np.log10(values + 1), bins=50)
        result["lengths"][name] = {
            "p50_p90_p99": np.percentile(values, [50, 90, 99]).tolist(),
            "histogram": histogram.tolist(),
            "bins": bins.tolist(),
        }
    return result


def traffic(processed: Path) -> Row:
    counts = np.asarray(pq.read_table(processed / "clicks_sku.parquet")["clicks"])
    ranked = np.sort(counts)[::-1]
    total = int(ranked.sum())
    shares = []
    for share in (0.01, 0.1, 0.5, 1.0):
        count = max(1, int(np.ceil(len(ranked) * share)))
        shares.append({"доля SKU": share, "доля кликов": float(ranked[:count].sum() / total)})
    return {"sku_with_clicks": len(counts), "clicks": total, "concentration": shares}


def sample_ids(processed: Path, seed: int, count: int) -> list[int]:
    splits = pq.read_table(processed / "splits.parquet")
    train = splits.filter(pc.equal(splits["split"], "train"))["sku_id"]
    cards = pq.read_table(processed / "cards.parquet", columns=["sku_id", "has_text"])
    kept = cards.filter(pc.and_(cards["has_text"], pc.is_in(cards["sku_id"], value_set=train)))
    return sorted(
        kept["sku_id"].to_pylist(),
        key=lambda sku: hashlib.sha256(f"{seed}:{sku}".encode()).digest(),
    )[:count]
