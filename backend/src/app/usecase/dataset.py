import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.catalog import Category, category_paths, split_offer
from app.domain.demand import ngrams, value_key
from app.domain.requirement import (
    AttributeUsage,
    CategoryUsage,
    candidate_attributes,
    rank_required,
)
from app.domain.split import Split, pick_new_categories, split_of
from app.usecase.dataset_ports import CatalogSource, ClickSource, DatasetStore, DescriptionSource
from app.usecase.interface import Logger


@dataclass(frozen=True, slots=True)
class PrepareConfig:
    seed: int = 42
    val_share: float = 0.1
    test_share: float = 0.1
    new_categories: int = 8
    new_category_min_cards: int = 200
    new_category_max_cards: int = 3000
    protected_categories: tuple[str, ...] = ("Смартфоны", "Ноутбуки")
    min_category_cards: int = 30
    candidates_per_category: int = 40
    top_n: int = 6
    min_coverage: float = 0.3
    values_per_attribute: int = 300


@dataclass(slots=True)
class PrepareReport:
    stats: dict[str, object] = field(default_factory=dict)


class PrepareDataset:
    def __init__(
        self,
        catalog: CatalogSource,
        descriptions: DescriptionSource,
        clicks: ClickSource,
        store: DatasetStore,
        logger: Logger,
    ) -> None:
        self._catalog = catalog
        self._descriptions = descriptions
        self._clicks = clicks
        self._store = store
        self._logger = logger

    def run(self, config: PrepareConfig) -> PrepareReport:
        started = time.monotonic()
        sku_clicks = self._clicks.sku_clicks()
        self._logger.info("clicks_loaded", skus=len(sku_clicks))
        desc_ids = self._descriptions.sku_ids()
        self._logger.info("descriptions_loaded", skus=len(desc_ids))

        categories: list[Category] = []
        sku_category: dict[int, int] = {}
        gold_skus: set[int] = set()
        attr_cards: Counter[tuple[int, str]] = Counter()
        attr_clicks: Counter[tuple[int, str]] = Counter()
        cat_cards: Counter[int] = Counter()
        cat_clicks: Counter[int] = Counter()
        attribute_cards: Counter[str] = Counter()
        offers = 0
        for item in self._catalog.items():
            if isinstance(item, Category):
                categories.append(item)
                continue
            offers += 1
            split = split_offer(item)
            self._store.add_offer(split.card, split.gold)
            if item.category_id is None:
                continue
            category = item.category_id
            clicks = sku_clicks.get(item.sku_id, 0)
            sku_category[item.sku_id] = category
            cat_cards[category] += 1
            cat_clicks[category] += clicks
            if split.gold:
                gold_skus.add(item.sku_id)
            for value in split.gold:
                attr_cards[category, value.attribute] += 1
                attr_clicks[category, value.attribute] += clicks
                attribute_cards[value.attribute] += 1
            if offers % 100_000 == 0:
                self._logger.info("offers_progress", offers=offers)
        self._store.close_offers()
        self._logger.info("offers_loaded", offers=offers, categories=len(categories))
        text = self._store.attach_texts()
        self._logger.info("cards_written", cards=text.cards)

        paths = category_paths(categories)
        self._store.write_categories(categories, paths)
        self._store.write_clicks(sku_clicks, sku_category)

        usages: dict[int, dict[str, AttributeUsage]] = defaultdict(dict)
        for (category, attribute), cards in attr_cards.items():
            usages[category][attribute] = AttributeUsage(
                attribute, cards, attr_clicks[category, attribute]
            )
        eligible = [c for c, n in cat_cards.items() if n >= config.min_category_cards]
        candidates = {
            c: candidate_attributes(
                usages[c],
                CategoryUsage(c, cat_cards[c], cat_clicks[c], 0),
                config.candidates_per_category,
            )
            for c in eligible
        }
        index = self._value_index(candidates, sku_category, config.values_per_attribute)
        mentions, query_clicks = self._count_mentions(index, sku_category)

        category_usage = [
            CategoryUsage(c, cat_cards[c], cat_clicks[c], query_clicks.get(c, 0))
            for c in sorted(cat_cards)
        ]
        self._store.write_category_usage(category_usage)
        required = [
            row
            for usage in category_usage
            if usage.category_id in candidates
            for row in rank_required(
                usage,
                usages[usage.category_id],
                mentions.get(usage.category_id, {}),
                config.top_n,
                config.min_coverage,
            )
        ]
        self._store.write_required(required)

        protected = {c.category_id for c in categories if c.name in config.protected_categories}
        gold_sizes = Counter(sku_category[s] for s in gold_skus)
        new_categories = pick_new_categories(
            gold_sizes,
            config.seed,
            config.new_categories,
            config.new_category_min_cards,
            config.new_category_max_cards,
            protected,
        )
        held_out = set(new_categories)
        splits = {
            sku: Split.NEW_CATEGORY
            if sku_category.get(sku) in held_out
            else split_of(sku, config.seed, config.val_share, config.test_share)
            for sku in sku_category
        }
        self._store.write_splits(splits)

        offer_ids = set(sku_category)
        click_ids = set(sku_clicks)
        stats: dict[str, object] = {
            "skus": {
                "sku_desc": len(desc_ids),
                "catalog_offers": offers,
                "catalog_offers_with_category": len(offer_ids),
                "query_clicks_unique": len(click_ids),
                "offers_and_desc": len(offer_ids & desc_ids),
                "offers_and_clicks": len(offer_ids & click_ids),
                "desc_and_clicks": len(desc_ids & click_ids),
                "all_three": len(offer_ids & desc_ids & click_ids),
                "gold_skus": len(gold_skus),
                "gold_skus_with_desc": len(gold_skus & desc_ids),
            },
            "cards": {
                "total": text.cards,
                "with_text": text.cards_with_text,
                "in_catalog": text.cards_in_catalog,
                "with_spec_block": text.cards_with_spec_block,
            },
            "top_attributes": attribute_cards.most_common(40),
            "categories": {
                "total": len(categories),
                "with_offers": len(cat_cards),
                "eligible": len(eligible),
                "new_category_ids": new_categories,
                "new_category_paths": [paths.get(c, "") for c in new_categories],
            },
            "splits": dict(Counter(str(s) for s in splits.values())),
            "required_rows": len(required),
            "seconds": round(time.monotonic() - started, 1),
        }
        self._store.write_stats(stats)
        return PrepareReport(stats)

    def _value_index(
        self,
        candidates: Mapping[int, Sequence[str]],
        sku_category: Mapping[int, int],
        limit: int,
    ) -> dict[int, dict[str, set[str]]]:
        wanted = frozenset(a for attrs in candidates.values() for a in attrs)
        counts: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
        for value in self._store.gold_values(wanted):
            category = sku_category.get(value.sku_id)
            if category is None or value.attribute not in candidates.get(category, ()):
                continue
            key = value_key(value.value, value.unit)
            if key:
                counts[category, value.attribute][key] += 1
        index: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for (category, attribute), counter in counts.items():
            for key, _ in counter.most_common(limit):
                index[category][key].add(attribute)
        self._logger.info("value_index_built", categories=len(index))
        return index

    def _count_mentions(
        self, index: Mapping[int, Mapping[str, set[str]]], sku_category: Mapping[int, int]
    ) -> tuple[dict[int, Counter[str]], Counter[int]]:
        mentions: dict[int, Counter[str]] = defaultdict(Counter)
        query_clicks: Counter[int] = Counter()
        rows = 0
        for stat in self._clicks.category_queries(sku_category):
            rows += 1
            query_clicks[stat.category_id] += stat.clicks
            keys = index.get(stat.category_id)
            if not keys:
                continue
            hit: set[str] = set()
            for gram in ngrams(stat.query):
                attributes = keys.get(gram)
                if attributes:
                    hit |= attributes
            for attribute in hit:
                mentions[stat.category_id][attribute] += stat.clicks
        self._logger.info("query_mentions_counted", category_queries=rows)
        return mentions, query_clicks
