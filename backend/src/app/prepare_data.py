import argparse
import hashlib
import json
import resource
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.adapter.catalog.yml_catalog import PickledYmlCatalog
from app.adapter.dataset.parquet_store import ParquetDatasetStore
from app.adapter.dataset.sources import ParquetClicks, ParquetDescriptions
from app.adapter.log.stdlib import StdlibLogger, configure
from app.usecase.dataset import PrepareConfig, PrepareDataset

RAW_NAMES = ("sku_desc.parquet", "query_clicks.parquet", "skus.pkl")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare organizer files without model calls")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    raw = args.raw.resolve()
    output = args.out.resolve()
    stage = output.with_name(output.name + ".building")
    if args.threads < 1:
        parser.error("--threads must be positive")
    if output.exists() or stage.exists():
        parser.error(f"Output or staging directory already exists: {output}; choose a new --out")
    for name in RAW_NAMES:
        if not (raw / name).is_file():
            parser.error(f"Missing organizer source: {raw / name}")
    for name, columns in (
        ("sku_desc.parquet", {"sku_id", "title", "description"}),
        ("query_clicks.parquet", {"sku_id", "toValidUTF8(query_text)"}),
    ):
        missing = columns - set(pq.ParquetFile(raw / name).schema_arrow.names)
        if missing:
            parser.error(f"{name} is missing columns: {sorted(missing)}")
    print("Hashing organizer source files", flush=True)
    sources = {
        name: {"sha256": digest(raw / name), "bytes": (raw / name).stat().st_size}
        for name in RAW_NAMES
    }
    configure()
    pa.set_cpu_count(args.threads)
    pa.set_io_thread_count(args.threads)
    config = PrepareConfig(seed=args.seed)
    store = ParquetDatasetStore(stage, raw / "sku_desc.parquet")
    usecase = PrepareDataset(
        PickledYmlCatalog(raw / "skus.pkl"),
        ParquetDescriptions(raw / "sku_desc.parquet"),
        ParquetClicks(raw / "query_clicks.parquet"),
        store,
        StdlibLogger("dataset"),
    )
    report = usecase.run(config)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mib = peak / (1024 * 1024 if sys.platform == "darwin" else 1024)
    manifest = {
        "version": "organizer-dataset-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "sources": sources,
        "outputs": {
            path.name: {
                "sha256": digest(path),
                "rows": pq.ParquetFile(path).metadata.num_rows,
                "bytes": path.stat().st_size,
            }
            for path in sorted(stage.glob("*.parquet"))
        },
        "configuration": asdict(config),
        "threads": args.threads,
        "peak_rss_mib": peak_mib,
        "gold_policy": "*_search plus catalog vendor/model; never copied into seller input",
        "metadata_policy": "Required fields/weights use catalog and traffic metadata across splits; not claimed train-only",
        "model_calls": 0,
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    stage.rename(output)
    print(
        json.dumps(
            {
                "output": str(output),
                "seconds": report.stats["seconds"],
                "peak_rss_mib": round(peak_mib, 1),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
