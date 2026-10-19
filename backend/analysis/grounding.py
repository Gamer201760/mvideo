import re
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from analysis.overview import Row, sample_ids
from app.domain.card_text import clean_text


def normalized(value: str | None) -> str:
    return " ".join(clean_text(value).casefold().replace("ё", "е").split())


def grounding(processed: Path, count: int = 20_000, seed: int = 20261019) -> Row:
    ids = sample_ids(processed, seed, count)
    cards = {
        row["sku_id"]: row
        for row in pq.read_table(
            processed / "cards.parquet",
            columns=["sku_id", "category_id", "title", "description", "seller_params"],
            filters=[("sku_id", "in", ids)],
        ).to_pylist()
    }
    texts = {
        sku: normalized((row["title"] or "") + "\n" + (row["description"] or ""))
        for sku, row in cards.items()
    }
    without_spec = {
        sku: normalized(
            (row["title"] or "")
            + "\n"
            + re.sub(r"(?is)характеристик[а-яё]*\s*:.*", "", row["description"] or "")
        )
        for sku, row in cards.items()
    }
    required: dict[int, set[str]] = defaultdict(set)
    for row in pq.read_table(processed / "required_attributes.parquet").to_pylist():
        required[row["category_id"]].add(row["attribute"])
    selected = pa.array(ids, type=pa.int64())
    total: Counter[str] = Counter()
    present: Counter[str] = Counter()
    no_spec: Counter[str] = Counter()
    seller_pairs = seller_matches = 0
    for batch in pq.ParquetFile(processed / "gold.parquet").iter_batches(100_000):
        kept = batch.filter(pc.is_in(batch.column("sku_id"), value_set=selected))
        for row in kept.to_pylist():
            sku, attribute = row["sku_id"], row["attribute"]
            value = normalized(row["value"])
            if not value or attribute not in required[cards[sku]["category_id"]]:
                continue
            total[attribute] += 1
            present[attribute] += value in texts[sku]
            no_spec[attribute] += value in without_spec[sku]
            for param in cards[sku]["seller_params"] or []:
                if param["name"] == attribute:
                    seller_pairs += 1
                    seller_matches += normalized(param["value"]) == value
    pairs = sum(total.values())
    return {
        "sample_size": len(ids),
        "seed": seed,
        "split": "train",
        "required_gold_pairs": pairs,
        "literal_overlap": sum(present.values()) / pairs if pairs else 0,
        "literal_overlap_without_spec": sum(no_spec.values()) / pairs if pairs else 0,
        "seller_gold_pairs": seller_pairs,
        "seller_literal_match": seller_matches / seller_pairs if seller_pairs else None,
        "attributes": [
            {
                "атрибут": name,
                "пар": number,
                "в тексте, %": 100 * present[name] / number,
                "без блока, %": 100 * no_spec[name] / number,
            }
            for name, number in total.most_common()
        ],
        "interpretation": "Literal overlap is not a semantic recall ceiling; equivalent units, synonyms and labels absent from the text need separate analysis",
    }
