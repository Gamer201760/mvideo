import argparse
import json
import resource
from pathlib import Path

from app.adapter.dataset.baseline_sink import FileReportSink
from app.adapter.dataset.final_files import JsonlAllCardsSource, JsonlRecordSink
from app.adapter.dataset.twin_source import ParquetTwinSource
from app.adapter.log.stdlib import StdlibLogger, configure
from app.adapter.ranker.fusion_store import load_fusion, save_fusion
from app.adapter.ranker.isotonic import IsotonicCalibrator
from app.usecase.final import FinalConfig, RunFinal
from app.usecase.final_all import FuseAllCards
from app.usecase.final_report import render_final_markdown

DEFAULT_DATA = Path("data/processed")
DEFAULT_OUT = Path("data/predictions")
DEFAULT_REPORTS = Path("reports")
DEFAULT_MODEL = Path("data/models/fusion")
NAME = "final"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fuse stage predictions and evaluate the result")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--all-cards", action="store_true",
                        help="fuse ranker predictions for every card with a saved fusion model")
    parser.add_argument("--shards", type=Path, nargs="*", default=[],
                        help="directories with <ranker>_all and <ranker>_all_baseline files")
    parser.add_argument("--ranker-name", default="ranker_final")
    return parser.parse_args(argv)


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    usecase = RunFinal(ParquetTwinSource(args.data, args.out), IsotonicCalibrator,
                       StdlibLogger("final"))
    report, model = usecase.run(FinalConfig(ranker_val=f"{args.ranker_name}_val",
                                            ranker_eval=args.ranker_name))
    FileReportSink(args.reports, NAME).write(report, render_final_markdown(report))
    save_fusion(model, args.model)
    rows = report["ablation"]
    summary = [r for r in rows if isinstance(r, dict) and r.get("group") == "all"] \
        if isinstance(rows, list) else []
    return {"threshold": model.threshold, "ece": report["ece"], "all": summary}


def fuse_all(args: argparse.Namespace) -> dict[str, object]:
    model = load_fusion(args.model)
    shards = args.shards or [args.out]
    usecase = FuseAllCards(JsonlAllCardsSource(shards, args.ranker_name, args.out),
                           JsonlRecordSink(args.out / f"{NAME}_all.predictions.jsonl"),
                           StdlibLogger("final"))
    config = FinalConfig()
    summary = usecase.run(model.rules, model.calibrate, model.threshold,
                          decision=config.decision_eval, twins=config.twins)
    args.reports.mkdir(parents=True, exist_ok=True)
    (args.reports / f"{NAME}_all.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure()
    summary = fuse_all(args) if args.all_cards else evaluate(args)
    summary["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
