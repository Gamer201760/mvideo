import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from app.adapter.dataset.stand_pack_file import StandPackFile
from app.adapter.decision.lexical import LexicalDecisionModel
from app.adapter.decision.system_one import SystemOneModel
from app.adapter.llm.openai_compat import OpenAICompatModel
from app.adapter.log.stdlib import StdlibLogger
from app.adapter.ranker.fusion_store import has_fusion, has_ranker, load_fusion, load_ranker
from app.adapter.system.clock import SystemClock, UuidIds
from app.adapter.twin.tfidf_index import TfidfTitleIndex
from app.adapter.twin.twin_store import has_twin_model, load_twin_model
from app.controller.errors import ErrorHandlers
from app.controller.router import api_router_v1
from app.domain.inference import Tier
from app.repository.memory.review import MemoryAliasRepository, MemoryReviewRepository
from app.settings import DecisionProvider, LanguageProvider, Settings, load_settings
from app.text_composition import TextServices, build_cache, build_openai_language, build_text
from app.usecase.extract_card import BaselineChooser, ExtractCard
from app.usecase.interface import DecisionModel, LanguageModel, Logger
from app.usecase.review_queue import ReviewQueue
from app.usecase.stand_catalog import StandCatalog
from app.usecase.stand_chooser import FusedChooser, FusionPolicy
from app.usecase.stand_ports import CandidateChooser, StandPack
from app.usecase.stand_twins import StandTwins, TwinSettings


@dataclass(frozen=True, slots=True)
class Providers:
    decision: DecisionModel
    language: LanguageModel | None
    logger: Logger

    async def aclose(self) -> None:
        await self.decision.aclose()
        if isinstance(self.language, OpenAICompatModel):
            await self.language.aclose()


@dataclass(frozen=True, slots=True)
class StandServices:
    extract: ExtractCard
    review: ReviewQueue
    catalog: StandCatalog
    text: TextServices

    async def aclose(self) -> None:
        await self.text.aclose()


def build_stand(settings: Settings, logger: Logger,
                language: LanguageModel | None = None) -> StandServices:
    pack = StandPackFile(Path(settings.stand_pack)).load()
    if pack is None:
        logger.warning("stand_pack_missing", path=settings.stand_pack)
    else:
        logger.info("stand_pack_loaded", categories=len(pack.categories),
                    examples=len(pack.examples))
    reviews, aliases, clock = MemoryReviewRepository(), MemoryAliasRepository(), SystemClock()
    extract = ExtractCard(pack, aliases, reviews,
                          build_chooser(Path(settings.stand_models), logger, pack),
                          clock, UuidIds())
    return StandServices(
        extract=extract,
        review=ReviewQueue(reviews, aliases, clock),
        catalog=StandCatalog(pack),
        text=build_text(settings, extract, language, logger),
    )


def build_twins(models: Path, logger: Logger, pack: StandPack | None) -> StandTwins | None:
    twin_dir = models / "twins"
    if pack is None or not pack.twins or not has_twin_model(twin_dir):
        logger.warning("stand_twins_missing", path=str(twin_dir))
        return None
    calibrator, threshold = load_twin_model(twin_dir)
    logger.info("stand_twins_loaded", entries=len(pack.twins), threshold=threshold)
    return StandTwins(pack.twins, TfidfTitleIndex(min_df=1), calibrator,
                      TwinSettings(threshold=threshold))


def build_chooser(models: Path, logger: Logger,
                  pack: StandPack | None = None) -> CandidateChooser:
    ranker_dir, fusion_dir = models / "ranker", models / "fusion"
    if not (has_ranker(ranker_dir) and has_fusion(fusion_dir)):
        logger.warning("stand_models_missing", path=str(models))
        return BaselineChooser()
    model, calibrator, threshold = load_ranker(ranker_dir)
    fusion = load_fusion(fusion_dir)
    logger.info("stand_models_loaded", path=str(models), threshold=fusion.threshold)
    policy = FusionPolicy(fusion.rules, fusion.calibrate, fusion.threshold)
    return FusedChooser(model, calibrator, threshold, policy, build_twins(models, logger, pack))


def build_decision_model(settings: Settings, retries: int = 0) -> DecisionModel:
    match settings.decision_provider:
        case DecisionProvider.LEXICAL:
            return LexicalDecisionModel()
        case DecisionProvider.SYSTEM_ONE:
            name = settings.decision_model_name
            return SystemOneModel(
                base_url=settings.decision_url,
                api_key=settings.decision_api_key,
                models={Tier.FAST: name, Tier.SMART: name},
                timeout_s=settings.decision_timeout_s,
                retries=retries,
            )


def build_language_model(settings: Settings) -> LanguageModel | None:
    match settings.language_provider:
        case LanguageProvider.NONE:
            return None
        case LanguageProvider.OPENAI:
            return build_openai_language(settings, build_cache(settings))



def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or load_settings(os.environ)
    language = build_language_model(config)
    logger = StdlibLogger("app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        providers = Providers(
            decision=build_decision_model(config), language=language, logger=logger
        )
        app.state.providers = providers
        stand = build_stand(config, logger, language)
        app.state.stand = stand
        try:
            yield
        finally:
            await stand.aclose()
            await providers.aclose()

    app = FastAPI(title="app", lifespan=lifespan)
    ErrorHandlers(logger).register(app)
    app.include_router(api_router_v1)
    return app
