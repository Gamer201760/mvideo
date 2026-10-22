import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from benchmarks.dataset import catalog, required_fields


def create_catalog(data: Path, output: Path, seed: int = 20261020) -> dict[str, Any]:
    fields, _ = required_fields(data)
    training = {
        row["sku_id"]
        for row in pq.read_table(data / "splits.parquet").to_pylist()
        if row["split"] == "train"
    }
    schemas, _, profile_cards = catalog(data, fields, training, seed)
    payload = {
        "format": "production-rules-catalog-v1",
        "seed": seed,
        "categories": [asdict(schemas[key]) for key in sorted(schemas)],
        "profile_cards": profile_cards,
        "profile_policy": "At most 20 train-split SKUs per category, SHA256(seed:sku_id) order",
        "vocabulary_policy": "Up to 8 observed training catalog values per required field",
        "input_policy": "No gold fields copied into extraction input",
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    return payload
