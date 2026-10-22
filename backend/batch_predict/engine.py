from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from threadpoolctl import threadpool_limits

from app.domain.acceptance import AcceptancePolicy
from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import CatalogCandidate, FlowCard
from app.domain.card_text import SellerParam, build_card_text
from app.domain.evidence_risk import assess_extraction
from app.domain.evidence_validation import validate_extraction
from app.domain.regex_answers import regex_answers
from app.domain.seller_completion import complete_seller_fields
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from batch_predict.catalog import read_catalog

SCHEMAS: dict[int, CatalogCandidate] = {}
POLICY = AcceptancePolicy()
RETRIEVAL: CatalogRetrieval | None = None


def initialize(catalog_path: str) -> None:
    global SCHEMAS, RETRIEVAL
    threadpool_limits(limits=1)
    SCHEMAS = read_catalog(Path(catalog_path))
    RETRIEVAL = CatalogRetrieval(SCHEMAS, ())


def predict(
    row: dict[str, Any],
    text: str | None = None,
    candidates: tuple[CatalogCandidate, ...] | None = None,
) -> dict[str, Any]:
    identity, category_id = row["sku_id"], row["category_id"]
    base = {"id": identity, "input_category_id": category_id, "engine": "rules"}
    try:
        text = (
            text
            if text is not None
            else build_card_text(
                row["title"],
                row["description"],
                tuple(SellerParam(**param) for param in row["seller_params"] or []),
            ).text
        )
        if candidates is None:
            candidates = (
                RETRIEVAL.retrieve(text, k=3) if RETRIEVAL is not None and text.strip() else ()
            )
        supplied = SCHEMAS.get(category_id)
        schema = (
            next(
                (candidate for candidate in candidates if candidate.category_id == category_id),
                supplied,
            )
            if category_id is not None
            else (candidates[0] if candidates else None)
        )
        selected_id = schema.category_id if schema else category_id
        base["category_source"] = (
            "input" if category_id is not None else "retrieved" if schema else "unclassified"
        )
        base["category_candidates"] = [
            {"category_id": candidate.category_id, "score": candidate.score}
            for candidate in candidates
        ]
        status = (
            "unclassified"
            if category_id is None and schema is None
            else "no_schema"
            if schema is None
            else "ok"
        )
        if not text.strip():
            status = "empty_input"
        if schema is None or status == "empty_input":
            return {
                **base,
                "status": status,
                "result": {
                    "category_id": selected_id,
                    "category_path": schema.path if schema else None,
                    "category_source": base["category_source"],
                    "text": text,
                    "values": [],
                    "missing": [field.attribute for field in schema.fields] if schema else [],
                    "rejections": [],
                    "validation_errors": [],
                },
            }
        rules = regex_answers(text, schema)
        card = FlowCard(identity, text, (schema,) if category_id is not None else candidates, rules)
        field_names = list(
            dict.fromkeys(
                field.attribute for candidate in card.candidates for field in candidate.fields
            )
        )
        field_ids = {name: index for index, name in enumerate(field_names)}
        extraction = parse_batch(
            {
                "c": [
                    {
                        "i": 0,
                        "k": 0,
                        "r": [],
                        "a": [
                            {
                                "f": field_ids[answer.attribute],
                                "v": answer.value,
                                "u": answer.unit,
                                "q": answer.quote,
                                "r": answer.risks,
                            }
                            for answer in rules
                        ],
                    }
                ]
            },
            (card,),
        )[0]
        sources = {
            (answer.attribute, answer.value, answer.quote): answer.source for answer in rules
        }
        extraction = replace(
            extraction,
            items=tuple(
                replace(
                    answer,
                    source=sources.get(
                        (answer.attribute, answer.value, answer.quote), answer.source
                    ),
                )
                for answer in extraction.items
            ),
        )
        extraction = complete_seller_fields(
            extraction,
            schema,
            text,
            tuple(SellerParam(**param) for param in row["seller_params"] or []),
        )
        extraction = validate_extraction(extraction, schema.fields, text, schema)
        card = FlowCard(identity, text, (schema,) if category_id is not None else candidates, rules)
        risks = {risk.attribute: risk for risk in assess_extraction(card, extraction)}
        values = [
            {
                "attribute": answer.attribute,
                "value": answer.normalized_value
                if answer.normalized_value is not None
                else answer.value,
                "unit": answer.normalized_unit
                if answer.normalized_unit is not None
                else answer.unit,
                "quote": answer.quote,
                "start": answer.start,
                "end": answer.end,
                "source": answer.source,
                "status": "accepted"
                if POLICY.accepts(risks.get(answer.attribute), selected_id)
                else "review",
                "risk": asdict(risks[answer.attribute]) if answer.attribute in risks else None,
            }
            for answer in (*extraction.items, *extraction.extra_fields)
        ]
        found = {answer.attribute for answer in extraction.items}
        return {
            **base,
            "status": status,
            "result": {
                "category_id": selected_id,
                "category_path": schema.path,
                "category_source": base["category_source"],
                "text": text,
                "values": values,
                "missing": [
                    field.attribute for field in schema.fields if field.attribute not in found
                ],
                "rejections": [asdict(rejection) for rejection in extraction.rejections],
                "validation_errors": list(extraction.validation_errors),
            },
        }
    except (ArithmeticError, LookupError, RuntimeError, TypeError, ValueError) as error:
        return {**base, "status": "error", "error": {"code": type(error).__name__}}


def predict_batch(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    texts: list[str | None] = []
    for row in rows:
        try:
            texts.append(
                build_card_text(
                    row["title"],
                    row["description"],
                    tuple(SellerParam(**param) for param in row["seller_params"] or []),
                ).text
            )
        except (ArithmeticError, LookupError, RuntimeError, TypeError, ValueError):
            texts.append(None)
    indices = [index for index, text in enumerate(texts) if text is not None and text.strip()]
    queries = [texts[index] or "" for index in indices]
    found = RETRIEVAL.retrieve_many(queries, k=3) if RETRIEVAL is not None else ((),) * len(queries)
    by_index = dict(zip(indices, found, strict=True))
    return [predict(row, texts[index], by_index.get(index, ())) for index, row in enumerate(rows)]
