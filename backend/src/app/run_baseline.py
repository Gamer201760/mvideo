import argparse
import json
import resource
from pathlib import Path

from app.adapter.dataset.baseline_sink import FilePredictionSink, FileReportSink
from app.adapter.dataset.baseline_source import ParquetBaselineSource
from app.adapter.log.stdlib import StdlibLogger, configure
from app.usecase.baseline import EVAL_SPLITS, BaselineConfig, RunBaseline

DEFAULT_DATA = Path("data/processed")
DEFAULT_OUT = Path("data/predictions")
DEFAULT_REPORTS = Path("reports")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the rules baseline and evaluate it")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--all-cards", action="store_true",
                        help="predict every card with text instead of the evaluation splits")
    parser.add_argument("--splits", default=",".join(sorted(EVAL_SPLITS)),
                        help="comma-separated splits to predict and evaluate, e.g. val")
    parser.add_argument("--no-candidates", action="store_true")
    parser.add_argument("--batch", type=int, default=2000)
    args = parser.parse_args(argv)
    configure()
    splits = frozenset(s.strip() for s in args.splits.split(",") if s.strip())
    name = "baseline_all" if args.all_cards else (
        "baseline" if splits == EVAL_SPLITS else "baseline_" + "_".join(sorted(splits)))
    config = BaselineConfig(
        splits=None if args.all_cards else splits,
        evaluate=not args.all_cards,
        batch=args.batch,
    )
    usecase = RunBaseline(
        source=ParquetBaselineSource(args.data),
        sink=FilePredictionSink(args.out, name, candidates=not args.no_candidates),
        reports=FileReportSink(args.reports, name),
        logger=StdlibLogger("baseline"),
    )
    report = usecase.run(config)
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    groups = report.get("groups", {})
    summary = groups.get("all", {}) if isinstance(groups, dict) else {}
    print(json.dumps({"cards": report["cards"], "all": summary, "peak_rss_mb": peak_mb},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
