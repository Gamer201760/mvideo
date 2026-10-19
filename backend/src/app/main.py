import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from threadpoolctl import threadpool_limits

from app.adapter.dataset.demo_catalog import stand_pack
from app.adapter.llm.gateway import GatewayModel
from app.adapter.llm.local_rules import LocalRulesModel
from app.adapter.log.stdlib import StdlibLogger
from app.adapter.system.clock import SystemClock, UuidIds
from app.controller.errors import ErrorHandlers
from app.controller.router import api_router_v1
from app.domain.acceptance import AcceptancePolicy
from app.domain.rule_routing import RuleRoutingPolicy
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.repository.sqlite.facades import AliasRepository, ReviewRepository
from app.repository.sqlite.uow import SqliteUnitOfWork
from app.settings import Settings, load_settings
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.extract_card import BaselineChooser, ExtractCard
from app.usecase.interface import LanguageModel
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.persistent_review import PersistentReview
from app.usecase.review_queue import ReviewQueue
from app.usecase.run_history import RunHistory
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_catalog import StandCatalog


@dataclass(frozen=True, slots=True)
class StandServices:
    extract: ExtractCard
    review: ReviewQueue
    catalog: StandCatalog
    flow: StandAttributeFlow
    history: RunHistory


def create_app(settings: Settings | None = None, model: LanguageModel | None = None) -> FastAPI:
    config = settings or load_settings()
    logger = StdlibLogger("attributes")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        factory: UnitOfWorkFactory = lambda: SqliteUnitOfWork(config.database)
        async with factory() as unit:
            categories = await unit.catalog.all()
        if not categories:
            raise RuntimeError("Catalog is empty; run migrations and python -m app.seed")
        pack = await asyncio.to_thread(stand_pack, categories)
        schemas = {c.category_id: c for c in categories}
        with threadpool_limits(limits=2):
            retrieval = await asyncio.to_thread(CatalogRetrieval, schemas, ())
        language = model or (
            GatewayModel(
                config.gateway_url, "default", config.gateway_key, timeout_s=config.gateway_timeout
            )
            if config.gateway_key
            else LocalRulesModel()
        )
        reviews, aliases = ReviewRepository(factory), AliasRepository(factory)
        clock = SystemClock()
        history = RunHistory(factory, clock, UuidIds())
        await history.recover()
        app.state.stand = StandServices(
            ExtractCard(
                pack, aliases, reviews, BaselineChooser(), clock, UuidIds(), factory, retrieval
            ),
            ReviewQueue(reviews, aliases, clock, PersistentReview(factory)),
            StandCatalog(pack, retrieval),
            StandAttributeFlow(
                AttributeFlow(
                    language,
                    FlowConfig(
                        batch_size=config.batch_size,
                        concurrency=config.concurrency,
                        max_batch_chars=config.max_batch_chars,
                        max_pending=config.max_pending,
                        timeout_s=config.gateway_timeout,
                    ),
                    RuleRoutingPolicy() if config.rules_first else None,
                ),
                retrieval,
                store=factory,
                acceptance=AcceptancePolicy(config.acceptance_threshold, config.auto_accept),
            ),
            history,
        )
        app.state.runtime = {
            "ready": True,
            "mode": "gateway" if config.gateway_key else "local_rules",
            "model": "default" if config.gateway_key else None,
            "categories": len(categories),
            "synthetic": True,
            "acceptance_threshold": config.acceptance_threshold,
            "auto_accept": config.auto_accept,
            "batch_size": config.batch_size,
            "concurrency": config.concurrency,
        }
        app.state.database = config.database
        try:
            yield
        finally:
            if isinstance(language, (GatewayModel, LocalRulesModel)):
                await language.aclose()

    app = FastAPI(title="Product attributes", version="0.2.0", lifespan=lifespan)
    ErrorHandlers(logger).register(app)
    app.include_router(api_router_v1)
    return app
