import argparse
import resource
from datetime import UTC, datetime
from pathlib import Path

from app.adapter.dataset.baseline_source import ParquetBaselineSource
from app.adapter.dataset.stand_pack_file import ParquetCategoryNames, StandPackFile
from app.adapter.dataset.twin_source import ParquetTwinSource
from app.adapter.log.stdlib import StdlibLogger, configure
from app.usecase.stand_pack import BuildStandPack, StandPackConfig

DEFAULT_DATA = Path("data/processed")
DEFAULT_OUT = Path("data/stand/pack.json.gz")
DEFAULTS = StandPackConfig()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the compact data pack for the demo stand")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--categories", type=int, default=DEFAULTS.categories)
    parser.add_argument("--examples", type=int, default=DEFAULTS.max_examples)
    parser.add_argument("--twins-per-category", type=int, default=DEFAULTS.twins_per_category,
                        help="train cards per category kept as catalog twins, 0 disables twins")
    args = parser.parse_args(argv)
    configure()
    logger = StdlibLogger("stand_pack")
    usecase = BuildStandPack(
        source=ParquetBaselineSource(args.data),
        names=ParquetCategoryNames(args.data),
        sink=StandPackFile(args.out),
        logger=logger,
        twin_rows=ParquetTwinSource(args.data, args.data) if args.twins_per_category else None,
    )
    config = StandPackConfig(categories=args.categories, max_examples=args.examples,
                             twins_per_category=args.twins_per_category)
    size = usecase.run(config, datetime.now(UTC))
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    logger.info("stand_pack_done", path=str(args.out), bytes=size, peak_rss_mb=peak_mb)


if __name__ == "__main__":
    main()
