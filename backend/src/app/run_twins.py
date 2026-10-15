import argparse
import json
import resource
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from app.adapter.dataset.baseline_sink import FileReportSink
from app.adapter.dataset.twin_all_files import ShardFiles, ShardTransferFiles
from app.adapter.dataset.twin_sink import FileTwinPredictionSink
from app.adapter.dataset.twin_source import ParquetTwinSource
from app.adapter.log.stdlib import StdlibLogger, configure
from app.adapter.ranker.isotonic import IsotonicCalibrator
from app.adapter.twin.tfidf_index import TfidfTitleIndex
from app.adapter.twin.twin_store import save_twin_model
from app.usecase.twin_all import TransferAllCards
from app.usecase.twins import RunTwins, TwinConfig

DEFAULT_DATA = Path("data/processed")
DEFAULT_OUT = Path("data/predictions")
DEFAULT_REPORTS = Path("reports")
NAME = "twins"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Transfer attributes from catalog twins")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--stage", default=TwinConfig().stage,
                        help="predictions file in --out to build on, e.g. ranker")
    parser.add_argument("--k", type=int, default=TwinConfig().k)
    parser.add_argument("--knn-batch", type=int, default=256)
    parser.add_argument("--batch", type=int, default=2000)
    parser.add_argument("--name", default=NAME)
    parser.add_argument("--splits", default=",".join(sorted(TwinConfig().splits)),
                        help="comma-separated splits to transfer onto and evaluate")
    parser.add_argument("--all-cards", action="store_true",
                        help="transfer onto every card of the shards in --work, no evaluation")
    parser.add_argument("--work", type=Path, default=Path("data/fusion_shards"))
    parser.add_argument("--shard-count", type=int, default=5)
    parser.add_argument("--save-model", type=Path, default=None,
                        help="directory for the twin calibrator and threshold (stand)")
    parser.add_argument("--prepare-only", action="store_true",
                        help="build the index, tune on val and save the model, no transfer")
    args = parser.parse_args(argv)
    configure()
    index = TfidfTitleIndex(batch=args.knn_batch)
    calibrator = IsotonicCalibrator()
    usecase = RunTwins(
        source=ParquetTwinSource(args.data, args.out),
        index=index,
        calibrator=calibrator,
        sink=FileTwinPredictionSink(args.out, args.name),
        reports=FileReportSink(args.reports, args.name),
        logger=StdlibLogger("twins"),
    )
    splits = frozenset(s.strip() for s in args.splits.split(",") if s.strip())
    config = TwinConfig(stage=args.stage, k=args.k, batch=args.batch, splits=splits)
    if args.all_cards or args.prepare_only:
        model = usecase.prepare(config)
        if args.save_model is not None:
            save_twin_model(calibrator, model.threshold, args.save_model)
        if args.prepare_only:
            print(json.dumps({"threshold": model.threshold,
                              "entries": len(model.context.data.entries)}))
            return
        transfer = TransferAllCards(ShardFiles(args.work, args.shard_count, args.stage), index,
                                    calibrator, ShardTransferFiles(args.work),
                                    StdlibLogger("twins"))
        result = transfer.run(model, config.k, config.floor, config.batch)
        result["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
        args.reports.mkdir(parents=True, exist_ok=True)
        (args.reports / f"{args.name}_all.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    report = usecase.run(config)
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    rows = cast(Sequence[Mapping[str, object]], report["ablation"])
    summary = next((r for r in rows if r["group"] == "all"), None)
    print(json.dumps({"cards": report["cards"], "threshold": report["threshold"],
                      "all": summary, "peak_rss_mb": peak_mb}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
