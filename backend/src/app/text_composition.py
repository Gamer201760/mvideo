from dataclasses import dataclass
from pathlib import Path

from app.adapter.cache.sqlite_cache import SqliteCache
from app.adapter.dataset.text_index_files import TextIndexFiles
from app.adapter.embeddings.catalog_search import (
    EMBEDDINGS_KIND,
    TFIDF_KIND,
    TfidfCatalogSearch,
    VectorCatalogSearch,
)
from app.adapter.embeddings.openai_compat import OpenAICompatEmbeddings
from app.adapter.llm.openai_compat import OpenAICompatModel
from app.domain.inference import Tier
from app.settings import ConfigError, Settings
from app.usecase.extract_card import ExtractCard
from app.usecase.interface import LanguageModel, Logger
from app.usecase.text_extract import ExtractText
from app.usecase.text_ports import CatalogSearch, TextIndex


@dataclass(frozen=True, slots=True)
class TextServices:
    extract: ExtractText
    index: TextIndex | None
    search: CatalogSearch | None
    embeddings: OpenAICompatEmbeddings | None

    async def aclose(self) -> None:
        if self.embeddings is not None:
            await self.embeddings.aclose()


def build_cache(settings: Settings) -> SqliteCache:
    return SqliteCache(Path(settings.text_cache))


def build_openai_language(settings: Settings, cache: SqliteCache | None) -> OpenAICompatModel:
    if not settings.llm_url or not settings.llm_api_key:
        raise ConfigError("LANGUAGE_MODEL=openai needs LLM_URL and LLM_API_KEY")
    return OpenAICompatModel(settings.llm_url, settings.llm_api_key,
                             {Tier.FAST: settings.llm_fast_model,
                              Tier.SMART: settings.llm_smart_model}, cache)


def build_embeddings(settings: Settings) -> OpenAICompatEmbeddings | None:
    if not settings.embeddings_url or not settings.embeddings_api_key:
        return None
    return OpenAICompatEmbeddings(settings.embeddings_url, settings.embeddings_api_key,
                                  settings.embeddings_model, settings.embeddings_dimensions,
                                  build_cache(settings))


def build_search(files: TextIndexFiles, index: TextIndex | None,
                 embeddings: OpenAICompatEmbeddings | None,
                 settings: Settings) -> CatalogSearch | None:
    if index is None:
        return None
    vector_ready = (embeddings is not None and EMBEDDINGS_KIND in index.models
                    and index.embedding_model == settings.embeddings_model
                    and index.dimensions == settings.embeddings_dimensions)
    if vector_ready and embeddings is not None:
        return VectorCatalogSearch(embeddings, files.vectors())
    if TFIDF_KIND in index.models:
        return TfidfCatalogSearch([e.title for e in index.entries])
    return None


def build_text(settings: Settings, cards: ExtractCard, language: LanguageModel | None,
               logger: Logger) -> TextServices:
    files = TextIndexFiles(Path(settings.text_index))
    index = files.load()
    embeddings = build_embeddings(settings) if index is not None else None
    search = build_search(files, index, embeddings, settings)
    if search is None:
        logger.warning("text_index_missing", path=settings.text_index)
    else:
        logger.info("text_index_loaded", entries=len(index.entries) if index else 0,
                    search=search.kind)
    return TextServices(ExtractText(index, search, cards, language), index, search, embeddings)
