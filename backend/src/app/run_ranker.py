import argparse
import json
import resource
from pathlib import Path

from app.adapter.dataset.baseline_sink import FilePredictionSink, FileReportSink
from app.adapter.dataset.ranker_source import ParquetRankerSource
from app.adapter.log.stdlib import StdlibLogger, configure
from app.adapter.ranker.catboost_model import CatBoostScoreModel
from app.adapter.ranker.fusion_store import load_ranker, save_ranker
from app.adapter.ranker.isotonic import IsotonicCalibrator
from app.usecase.ranker import RankerConfig, RunRanker
from app.usecase.ranker_predict import PredictRanker

DEFAULT_DATA = Path("data/processed")
DEFAULT_OUT = Path("data/predictions")
DEFAULT_REPORTS = Path("reports")
NAME = "ranker"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the candidate ranker and evaluate it")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--name", default=NAME)
    parser.add_argument("--train-modulo", type=int, default=RankerConfig().train_modulo,
                        help="use train cards whose sku_id is divisible by this number")
    parser.add_argument("--iterations", type=int, default=400)
    parser.add_argument("--threads", type=int, default=-1)
    parser.add_argument("--batch", type=int, default=2000)
    parser.add_argument("--write-val", action="store_true",
                        help="also write calibrated predictions for the val split")
    parser.add_argument("--save-model", type=Path, default=None)
    parser.add_argument("--load-model", type=Path, default=None,
                        help="skip training and predict every card with text with a saved model")
    return parser.parse_args(argv)


def train(args: argparse.Namespace) -> dict[str, object]:
    baseline_path = args.reports / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() \
        else None
    model = CatBoostScoreModel(iterations=args.iterations, threads=args.threads)
    calibrator = IsotonicCalibrator()
    val_sink = FilePredictionSink(args.out, f"{args.name}_val", candidates=False,
                                  calibrated=True) if args.write_val else None
    usecase = RunRanker(
        source=ParquetRankerSource(args.data),
        model=model,
        calibrator=calibrator,
        sink=FilePredictionSink(args.out, args.name, candidates=False, calibrated=True),
        reports=FileReportSink(args.reports, args.name),
        logger=StdlibLogger("ranker"),
        baseline_report=baseline,
        val_sink=val_sink,
    )
    report = dict(usecase.run(RankerConfig(train_modulo=args.train_modulo, batch=args.batch)))
    if args.save_model is not None:
        threshold = report["threshold"]
        value = threshold.get("value") if isinstance(threshold, dict) else threshold
        save_ranker(model, calibrator, float(str(value)), args.save_model)
    groups = report.get("groups", {})
    summary = groups.get("all", {}) if isinstance(groups, dict) else {}
    return {"cards": report["cards"], "all": summary}


def predict(args: argparse.Namespace) -> dict[str, object]:
    model, calibrator, threshold = load_ranker(args.load_model, args.threads)
    usecase = PredictRanker(
        source=ParquetRankerSource(args.data),
        model=model,
        calibrator=calibrator,
        sink=FilePredictionSink(args.out, f"{args.name}_all", candidates=False, calibrated=True),
        baseline_sink=FilePredictionSink(args.out, f"{args.name}_all_baseline", candidates=False),
        logger=StdlibLogger("ranker"),
    )
    cards = usecase.run(RankerConfig(batch=args.batch), threshold, None)
    return {"cards": cards, "threshold": threshold}


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure()
    summary = predict(args) if args.load_model is not None else train(args)
    summary["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
