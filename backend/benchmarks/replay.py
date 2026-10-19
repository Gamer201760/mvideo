import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from threadpoolctl import threadpool_limits

import app
from app.domain.card_text import SellerParam
from app.domain.inference import Completion, StructuredRequest, Usage
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput
from benchmarks.files import Row, digest, implementation, read_lines, write_json, write_lines
from benchmarks.run import IsolatedRetrieval, RecordedModel, load_schemas
from benchmarks.score import aggregate


def loaded_implementation() -> dict[str, str]:
    sources = {
        name: sha
        for name, sha in implementation().items()
        if not name.startswith("backend/src/app/")
    }
    root = Path(str(app.__file__)).parent
    sources.update(
        (f"backend/src/app/{p.relative_to(root)}", digest(p)) for p in root.rglob("*.py")
    )
    return sources


class SavedResponse:
    def __init__(self, call: Row) -> None:
        self.call = call
        self.used = False

    async def complete(self, request: StructuredRequest) -> Completion:
        if self.used:
            raise AssertionError("Replay requires exactly one saved response")
        for key, actual in (
            ("system", request.system),
            ("prompt", request.prompt),
            ("schema", request.schema),
        ):
            expected = self.call[key]
            if key == "prompt":
                actual, expected = json.loads(str(actual)), json.loads(expected)
            if actual != expected:
                raise AssertionError(f"Changed {key}: saved answers cannot evaluate a new request")
        self.used = True
        return Completion(self.call["response"], Usage(**self.call["usage"]))


async def replay(bundle: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Output exists; preserve prior replay artifacts")
    sources_before = loaded_implementation()
    protocol = json.loads((bundle / "protocol.json").read_text())
    for name, expected in protocol["artifacts_sha256"].items():
        if digest(bundle / name) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    sample = read_lines(bundle / "sample.jsonl")
    schemas = load_schemas(bundle / "catalog.json", set(protocol["withheld_category_ids"]))
    retrieval = CatalogRetrieval(schemas, ())
    profiles = json.loads((bundle / "profiles.json").read_text())
    weights = json.loads((bundle / "weights.json").read_text())
    predictions: dict[str, dict[int, Row]] = {}
    sources = {}
    for mode in protocol["modes"]:
        predictions[mode] = {}
        for row in sample:
            path = bundle / "results" / f"{mode}-{row['sku_id']}.json"
            saved = json.loads(path.read_text())
            sources[path.name] = digest(path)
            if saved["sku_id"] != row["sku_id"] or saved["mode"] != mode:
                raise ValueError(f"Saved response identity mismatch: {path.name}")
            if saved.get("error") or len(saved["calls"]) != 1:
                raise ValueError("Replay supports completed single-call records only")
            delegate = SavedResponse(saved["calls"][0])
            flow = StandAttributeFlow(
                AttributeFlow(RecordedModel(delegate, mode), FlowConfig(concurrency=1)),
                IsolatedRetrieval(retrieval, schemas),
            )
            card = CardInput(
                title=row["title"],
                description=row["description"] or "",
                seller_params=tuple(SellerParam(**p) for p in row["seller_params"] or []),
                category_id=None,
            )
            result = await flow.execute(card)
            if not delegate.used:
                raise AssertionError("Saved response was not consumed")
            predictions[mode][row["sku_id"]] = {
                **saved,
                "result": asdict(result),
                "evidence_exact": all(
                    result.text[a.start : a.end] == a.quote
                    for a in (*result.extraction.items, *result.extraction.extra_fields)
                    if a.status == "supported"
                ),
            }
    if loaded_implementation() != sources_before:
        raise ValueError("Implementation changed during replay; repeat in a stable snapshot")
    write_lines(
        output / "predictions.jsonl",
        (prediction for rows in predictions.values() for prediction in rows.values()),
    )
    write_json(
        output / "report.json",
        {
            "scope": "Saved-response replay; original latency/tokens are not new measurements",
            "new_model_calls": 0,
            "requests_equal": True,
            "protocol_sha256": digest(bundle / "protocol.json"),
            "results_sha256": sources,
            "implementation_sha256": sources_before,
            "results": {
                mode: aggregate(sample, rows, profiles, weights)
                for mode, rows in predictions.items()
            },
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        asyncio.run(replay(args.bundle, args.output))


if __name__ == "__main__":
    main()
