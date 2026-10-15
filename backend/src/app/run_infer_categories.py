import argparse
import json
import resource
from pathlib import Path

from app.adapter.category.classifier import TfidfLinearClassifier
from app.adapter.category.corpus import ParquetCategoryCorpus
from app.adapter.category.sink import ParquetCategorySink
from app.adapter.log.stdlib import StdlibLogger, configure
from app.usecase.category_inference import CategoryConfig, InferCategories

DEFAULT_DATA = Path("data/processed")
DEFAULT_RAW = Path("data/raw")
DEFAULT_REPORTS = Path("reports")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Infer categories for cards outside the catalog")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--target-precision", type=float,
                        default=CategoryConfig().target_precision)
    parser.add_argument("--ood-reject-share", type=float,
                        default=CategoryConfig().ood_reject_share)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    configure()
    usecase = InferCategories(
        corpus=ParquetCategoryCorpus(args.data, args.raw),
        classifier=TfidfLinearClassifier(seed=args.seed, jobs=args.jobs),
        sink=ParquetCategorySink(args.data, args.reports),
        logger=StdlibLogger("categories"),
    )
    report = usecase.run(CategoryConfig(target_precision=args.target_precision,
                                        ood_reject_share=args.ood_reject_share, seed=args.seed))
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    summary = {k: v for k, v in report.items() if k not in {"classifier_test", "coverage"}}
    print(json.dumps({**summary, "peak_rss_mb": peak_mb}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
