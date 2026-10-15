import argparse
import asyncio
import json
import os
import resource
from pathlib import Path

from app.adapter.dataset.baseline_sink import FilePredictionSink, FileReportSink
from app.adapter.dataset.baseline_source import ParquetBaselineSource
from app.adapter.dataset.category_tree import ParquetCategoryTree
from app.adapter.dataset.decision_cache import FileDecisionCache
from app.adapter.decision.lexical import MODEL_NAME as LEXICAL_MODEL
from app.adapter.log.stdlib import StdlibLogger, configure
from app.main import build_decision_model
from app.settings import DecisionProvider, load_settings
from app.usecase.baseline import EVAL_SPLITS
from app.usecase.decision_run import DecisionRunConfig, RunDecision
from app.usecase.decision_stage import StageConfig

DEFAULT_DATA = Path("data/processed")
DEFAULT_OUT = Path("data/predictions")
DEFAULT_REPORTS = Path("reports")
DEFAULT_CACHE = Path("data/decision_cache")
DEFAULT_ENV = Path("../.env")
RETRIES = 3


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pick attribute values with a decision model")
    parser.add_argument("--provider", choices=[p.value for p in DecisionProvider])
    parser.add_argument("--sample", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--splits", default=",".join(sorted(EVAL_SPLITS)))
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--override", type=float, default=0.5)
    parser.add_argument("--drop", type=float, default=None)
    parser.add_argument("--dictionary", action="store_true")
    parser.add_argument("--mix-k", type=int, default=0)
    parser.add_argument("--route-all", action="store_true")
    parser.add_argument("--route-below", type=float, default=0.6)
    parser.add_argument("--dictionary-k", type=int, default=20)
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument("--price-input-per-mtok", type=float, default=None)
    parser.add_argument("--price-output-per-mtok", type=float, default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> dict[str, object]:
    env = {**read_env_file(args.env_file), **os.environ}
    if args.provider:
        env["DECISION_MODEL"] = args.provider
    settings = load_settings(env)
    offline = settings.decision_provider is DecisionProvider.LEXICAL
    model_name = LEXICAL_MODEL if offline else settings.decision_model_name
    splits = frozenset(s.strip() for s in args.splits.split(",") if s.strip())
    name = args.name or f"decision_{settings.decision_provider.value}_" + "_".join(sorted(splits))
    config = DecisionRunConfig(
        stage=StageConfig(model_name=model_name, top_k=args.top_k,
                          dictionary_k=args.dictionary_k, min_confidence=args.min_confidence,
                          route_all=args.route_all, route_below=args.route_below,
                          dictionary=args.dictionary, mix_k=args.mix_k),
        provider=f"{settings.decision_provider.value}:{model_name}",
        offline=offline,
        splits=splits,
        sample=args.sample,
        seed=args.seed,
        concurrency=args.concurrency,
        price_input_per_mtok=args.price_input_per_mtok,
        price_output_per_mtok=args.price_output_per_mtok,
        max_cost_usd=args.max_cost_usd,
        override=args.override,
        drop=args.drop,
    )
    model = build_decision_model(settings, retries=RETRIES)
    try:
        usecase = RunDecision(
            source=ParquetBaselineSource(args.data),
            sink=FilePredictionSink(args.out, name, candidates=False),
            reports=FileReportSink(args.reports, name),
            model=model,
            logger=StdlibLogger("decision"),
            cache=FileDecisionCache(args.cache / model_name.replace("/", "_")),
            categories=ParquetCategoryTree(args.data),
        )
        return dict(await usecase.run(config))
    finally:
        await model.aclose()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure()
    report = asyncio.run(run(args))
    groups = report.get("groups", {})
    summary = groups.get("all", {}) if isinstance(groups, dict) else {}
    print(json.dumps({"cards": report["cards"], "all": summary, "usage": report["usage"],
                      "calibration": report["calibration"],
                      "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024},
                     ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
