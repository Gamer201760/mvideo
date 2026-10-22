import argparse
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from batch_predict.catalog_build import create_catalog
from batch_predict.engine import initialize, predict_batch
from batch_predict.writer import Shards, digest, save_json

COLUMNS = ["sku_id", "category_id", "title", "description", "seller_params"]


def chunks(path: Path, limit: int | None, size: int = 128) -> Any:
    seen = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=size, columns=COLUMNS):
        rows = batch.to_pylist()
        if limit is not None:
            rows = rows[: max(0, limit - seen)]
        if not rows:
            break
        yield rows
        seen += len(rows)
        if limit is not None and seen >= limit:
            break


def source_manifest(data: Path) -> dict[str, Any]:
    names = [
        "cards.parquet",
        "categories.parquet",
        "required_attributes.parquet",
        "splits.parquet",
        "gold.parquet",
    ]
    return {
        name: {
            "sha256": digest(data / name),
            "bytes": (data / name).stat().st_size,
            "rows": pq.ParquetFile(data / name).metadata.num_rows,
        }
        for name in names
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    if args.output.exists():
        raise FileExistsError("Output directory already exists")
    args.output.mkdir(parents=True)
    catalog_path = args.output / "catalog.json"
    if args.catalog is None:
        metadata = create_catalog(args.data, catalog_path)
    else:
        catalog_path.write_bytes(args.catalog.read_bytes())
        metadata = json.loads(catalog_path.read_text())
    source = source_manifest(args.data)
    expected = (
        min(args.limit, source["cards.parquet"]["rows"])
        if args.limit
        else source["cards.parquet"]["rows"]
    )
    manifest: dict[str, Any] = {
        "format": "full-rules-predictions-v1",
        "status": "running",
        "engine": "rules",
        "started_at": datetime.now(UTC).isoformat(),
        "expected_rows": expected,
        "sources": source,
        "catalog": {
            "file": "catalog.json",
            "sha256": digest(catalog_path),
            "categories": len(metadata["categories"]),
            "profile_cards": metadata["profile_cards"],
        },
        "execution": {
            "workers": args.workers,
            "batch_size": 128,
            "external_model_calls": 0,
            "category_policy": "Production CatalogRetrieval top3; supplied category overrides candidates as in StandAttributeFlow",
            "extractor": "production regex_answers, parse_batch, seller completion, evidence validation, risk and acceptance",
            "schema_policy": "Required fields and train-only catalog profile choices; no gold in per-card input",
            "ordering": "Original parquet row order",
            "max_compressed_shard_bytes": 32 * 1024 * 1024,
        },
        "scope": "Full-input execution artifact, not independent accuracy or confidence calibration",
    }
    code = Path(__file__).resolve().parents[1]
    manifest["implementation_sha256"] = {
        path.relative_to(code).as_posix(): digest(path)
        for folder in [code / "src/app", code / "batch_predict"]
        for path in sorted(folder.rglob("*.py"))
    }
    writer = Shards(args.output)
    input_ids = hashlib.sha256()
    batches = 0
    inference_started = time.perf_counter()
    with ProcessPoolExecutor(
        max_workers=args.workers, initializer=initialize, initargs=(str(catalog_path),)
    ) as pool:
        pending: list[Any] = []
        for rows in chunks(args.data / "cards.parquet", args.limit):
            for row in rows:
                input_ids.update(f"{row['sku_id']}\n".encode())
            pending.append(pool.submit(predict_batch, rows))
            if len(pending) >= args.workers * 2:
                for record in pending.pop(0).result():
                    writer.add(record)
                batches += 1
                if batches % 8 == 0:
                    manifest.update(writer.checkpoint())
                    manifest["elapsed_s"] = round(time.perf_counter() - inference_started, 3)
                    save_json(args.output / "manifest.json", manifest)
                    print(
                        json.dumps(
                            {"rows": writer.counts["rows"], "elapsed_s": manifest["elapsed_s"]}
                        ),
                        flush=True,
                    )
        for future in pending:
            for record in future.result():
                writer.add(record)
    writer.close()
    manifest.update(writer.checkpoint())
    manifest.update(
        {
            "input_id_stream_sha256": input_ids.hexdigest(),
            "elapsed_s": round(time.perf_counter() - inference_started, 3),
            "total_elapsed_s": round(time.perf_counter() - started, 3),
            "finished_at": datetime.now(UTC).isoformat(),
        }
    )
    if writer.counts["rows"] != expected or writer.identities.hexdigest() != input_ids.hexdigest():
        raise ValueError("Output row or ID coverage differs from the input")
    manifest["status"] = "completed"
    save_json(args.output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.workers < 1 or args.limit is not None and args.limit < 1:
        parser.error("workers and limit must be positive")
    print(json.dumps(execute(args)["counts"], indent=2))
