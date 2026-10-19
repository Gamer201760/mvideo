import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from threadpoolctl import threadpool_limits

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.acceptance import AcceptancePolicy
from app.domain.card_text import SellerParam
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput
from benchmarks.acceptance_packets import write_review_packet
from benchmarks.files import Row, digest, implementation, read_lines, write_json, write_lines
from benchmarks.run import IsolatedRetrieval, load_schemas


async def execute(bundle: Path, catalog: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Output exists; preserve fixed inference")
    protocol = json.loads((bundle / "protocol.json").read_text())
    if digest(bundle / "sample.jsonl") != protocol["sample_sha256"]:
        raise ValueError("Frozen sample changed")
    if digest(catalog) != protocol["catalog_sha256"]:
        raise ValueError("Frozen catalog changed")
    sources = implementation()
    policy = AcceptancePolicy(protocol["policy"]["threshold"], protocol["policy"]["enabled"])
    schemas = load_schemas(catalog, set())
    retrieval = CatalogRetrieval(schemas, ())
    records, packets = [], []
    for row in read_lines(bundle / "sample.jsonl"):
        flow = StandAttributeFlow(
            AttributeFlow(LocalRulesModel(), FlowConfig(concurrency=1)),
            IsolatedRetrieval(retrieval, schemas),
            acceptance=policy,
        )
        result = await flow.execute(
            CardInput(
                title=row["title"],
                description=row["description"] or "",
                seller_params=tuple(SellerParam(**p) for p in row["seller_params"] or []),
                category_id=None,
            )
        )
        answers = [
            answer
            for answer in (*result.extraction.items, *result.extraction.extra_fields)
            if answer.status == "supported"
        ]
        assessments = {risk.attribute: risk for risk in result.risks}
        record: Row = {
            "card_id": row["card_id"],
            "partition": row["partition"],
            "category_id": result.extraction.category_id,
            "answers": [],
            "automatic": result.automatic,
        }
        packet: Row = {
            "card_id": row["card_id"],
            "text": result.text,
            "category": result.category.path if result.category else None,
            "answers": [],
        }
        for i, answer in enumerate(answers):
            if result.text[answer.start : answer.end] != answer.quote:
                raise ValueError("Invalid evidence offsets")
            item = {
                "answer_id": f"{row['card_id']}:A{i + 1}",
                "attribute": answer.attribute,
                "value": answer.normalized_value
                if answer.normalized_value is not None
                else answer.value,
                "unit": answer.normalized_unit
                if answer.normalized_unit is not None
                else answer.unit,
                "quote": answer.quote,
            }
            packet["answers"].append(item)
            record["answers"].append({**item, "risk": asdict(assessments[answer.attribute])})
        records.append(record)
        packets.append(packet)
    if implementation() != sources:
        raise ValueError("Implementation changed during inference")
    write_lines(output / "predictions.jsonl", records)
    write_lines(output / "blind-review.jsonl", packets)
    write_review_packet(output, records, packets)
    write_json(
        output / "manifest.json",
        {
            "protocol_sha256": digest(bundle / "protocol.json"),
            "implementation_sha256": sources,
            "predictions_sha256": digest(output / "predictions.jsonl"),
            "blind_review_sha256": digest(output / "blind-review.jsonl"),
            "external_model_calls": 0,
            "provider": "local_rules",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("bundle", "catalog", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        asyncio.run(execute(args.bundle, args.catalog, args.output))


if __name__ == "__main__":
    main()
