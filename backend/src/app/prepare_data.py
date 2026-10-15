import argparse
import json
import resource
from pathlib import Path

from app.adapter.catalog.yml_catalog import PickledYmlCatalog
from app.adapter.dataset.parquet_store import ParquetDatasetStore
from app.adapter.dataset.sources import ParquetClicks, ParquetDescriptions
from app.adapter.log.stdlib import StdlibLogger, configure
from app.usecase.dataset import PrepareConfig, PrepareDataset

DEFAULT_RAW = Path("data/raw")
DEFAULT_OUT = Path("data/processed")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build processed dataset from organizer files")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=PrepareConfig().seed)
    args = parser.parse_args(argv)
    configure()
    raw: Path = args.raw
    descriptions = raw / "sku_desc.parquet"
    usecase = PrepareDataset(
        catalog=PickledYmlCatalog(raw / "skus.pkl"),
        descriptions=ParquetDescriptions(descriptions),
        clicks=ParquetClicks(raw / "query_clicks.parquet"),
        store=ParquetDatasetStore(args.out, descriptions),
        logger=StdlibLogger("prepare_data"),
    )
    report = usecase.run(PrepareConfig(seed=args.seed))
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(json.dumps({**report.stats, "peak_rss_mb": peak_mb}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
