import argparse
import asyncio
import json
import os
import resource
import sys
from dataclasses import asdict, replace
from pathlib import Path

from app.adapter.dataset.baseline_sink import FileReportSink
from app.adapter.dataset.stand_pack_file import ParquetCategoryNames, StandPackFile
from app.adapter.dataset.text_index_files import TextIndexFiles
from app.adapter.dataset.twin_source import ParquetTwinSource
from app.adapter.embeddings.catalog_search import TfidfCatalogSearch, VectorCatalogSearch
from app.adapter.log.stdlib import StdlibLogger, configure
from app.adapter.ranker.isotonic import IsotonicCalibrator
from app.main import build_stand
from app.run_decision import DEFAULT_ENV, read_env_file
from app.settings import Settings, load_settings
from app.text_composition import build_cache, build_embeddings, build_openai_language
from app.usecase.text_build import BuildTextIndex, TextIndexConfig
from app.usecase.text_eval import EvaluateText, TextEvalConfig
from app.usecase.text_ports import Spending
from app.usecase.text_report import render_text_report

DEFAULT_DATA = Path("../data/processed")
DEFAULT_STAND = Path("../data/stand")
DEFAULT_CACHE = Path("../data/cache/text.sqlite")
DEFAULT_REPORTS = Path("../reports")
REPORT_NAME = "raw_text"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract category, title and attributes "
                                                 "from plain product text")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--stand", type=Path, default=DEFAULT_STAND,
                        help="directory with pack.json.gz, models/ and text/")
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="build the catalog index and calibrate categories")
    index.add_argument("--per-category", type=int, default=TextIndexConfig().per_category)
    index.add_argument("--val-cards", type=int, default=TextIndexConfig().val_cards)
    index.add_argument("--seed", type=int, default=0)
    index.add_argument("--skip-embeddings", action="store_true",
                       help="keep the existing vectors and only recalibrate")
    evaluate = commands.add_parser("eval", help="evaluate on synthetic text from test cards")
    evaluate.add_argument("--test-cards", type=int, default=TextEvalConfig().test_cards)
    evaluate.add_argument("--new-cards", type=int, default=TextEvalConfig().new_cards)
    evaluate.add_argument("--seed", type=int, default=0)
    evaluate.add_argument("--budget-rub", type=float, default=TextEvalConfig().budget_rub)
    evaluate.add_argument("--concurrency", type=int, default=TextEvalConfig().concurrency)
    evaluate.add_argument("--no-llm", action="store_true", help="title by rule, no LLM calls")
    evaluate.add_argument("--tfidf", action="store_true", help="TF-IDF search, no embeddings")
    evaluate.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    evaluate.add_argument("--name", default=REPORT_NAME)
    text = commands.add_parser("text", help="extract from a text or HTML file, '-' for stdin")
    text.add_argument("path")
    text.add_argument("--no-llm", action="store_true")
    text.add_argument("--tfidf", action="store_true")
    args = parser.parse_args(argv)
    configure()
    defaults = {"STAND_PACK": str(args.stand / "pack.json.gz"),
                "STAND_MODELS": str(args.stand / "models"),
                "TEXT_INDEX": str(args.stand / "text"), "TEXT_CACHE": str(DEFAULT_CACHE)}
    settings = load_settings({**defaults, **read_env_file(args.env_file), **os.environ})
    match args.command:
        case "index":
            asyncio.run(_index(args, settings))
        case "eval":
            asyncio.run(_eval(args, settings))
        case "text":
            asyncio.run(_text(args, settings))
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    StdlibLogger("raw_extract").info("raw_extract_done", peak_rss_mb=peak_mb)


async def _index(args: argparse.Namespace, settings: Settings) -> None:
    logger = StdlibLogger("raw_extract")
    files = TextIndexFiles(Path(settings.text_index))
    usecase = BuildTextIndex(ParquetTwinSource(args.data, args.data), files, logger)
    config = TextIndexConfig(per_category=args.per_category, val_cards=args.val_cards,
                             seed=args.seed)
    embeddings = build_embeddings(settings)
    try:
        if not args.skip_embeddings:
            if embeddings is None:
                raise SystemExit("index needs EMBEDDINGS_URL and EMBEDDINGS_API_KEY")
            names = {c: n for c, (n, _) in ParquetCategoryNames(args.data).names().items()}
            await usecase.build(config, names, embeddings, settings.embeddings_model,
                                settings.embeddings_dimensions)
        index = files.load()
        if index is None:
            raise SystemExit(f"no index in {settings.text_index}")
        if embeddings is not None and (index.embedding_model, index.dimensions) != (
                settings.embeddings_model, settings.embeddings_dimensions):
            raise SystemExit("index vectors were built with another embedding model or size; "
                             "rebuild without --skip-embeddings")
        await usecase.calibrate(config, index.entries,
                                TfidfCatalogSearch([e.title for e in index.entries]),
                                IsotonicCalibrator())
        if embeddings is not None:
            await usecase.calibrate(config, index.entries,
                                    VectorCatalogSearch(embeddings, files.vectors()),
                                    IsotonicCalibrator())
            logger.info("text_index_spent", rub=embeddings.spent_rub())
    finally:
        if embeddings is not None:
            await embeddings.aclose()


async def _eval(args: argparse.Namespace, settings: Settings) -> None:
    logger = StdlibLogger("raw_extract")
    language = None if args.no_llm else build_openai_language(settings, build_cache(settings))
    stand = build_stand(_tfidf(settings, args.tfidf), logger, language)
    pack = StandPackFile(Path(settings.stand_pack)).load()
    if pack is None or stand.text.search is None:
        raise SystemExit("eval needs the stand pack and the text index")
    spending: list[Spending] = [s for s in (language, stand.text.embeddings) if s is not None]
    usecase = EvaluateText(ParquetTwinSource(args.data, args.data), stand.text.extract,
                           stand.extract, pack, spending, logger)
    config = TextEvalConfig(test_cards=args.test_cards, new_cards=args.new_cards,
                            seed=args.seed, budget_rub=args.budget_rub,
                            concurrency=args.concurrency)
    try:
        report = await usecase.run(config)
    finally:
        await stand.aclose()
        if language is not None:
            await language.aclose()
    report["search"] = stand.text.search.kind
    report["title_mode"] = "rule" if language is None else settings.llm_fast_model
    index = TextIndexFiles(Path(settings.text_index)).reports()
    FileReportSink(args.reports, args.name).write(report, render_text_report(report, index))


async def _text(args: argparse.Namespace, settings: Settings) -> None:
    raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    logger = StdlibLogger("raw_extract")
    language = None if args.no_llm else build_openai_language(settings, build_cache(settings))
    stand = build_stand(_tfidf(settings, args.tfidf), logger, language)
    try:
        result = await stand.text.extract.execute(raw)
    finally:
        await stand.aclose()
        if language is not None:
            await language.aclose()
    print(json.dumps(asdict(result), ensure_ascii=False, indent=1, default=str))


def _tfidf(settings: Settings, enabled: bool) -> Settings:
    return replace(settings, embeddings_api_key=None) if enabled else settings


if __name__ == "__main__":
    main()
