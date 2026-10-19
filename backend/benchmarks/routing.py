import argparse
import asyncio
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from threadpoolctl import threadpool_limits

from app.domain.card_text import SellerParam
from app.domain.errors import ModelFailure
from app.domain.inference import Completion, StructuredRequest, Usage
from app.domain.rule_routing import RuleRoutingPolicy, route_rules
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput
from benchmarks.files import Row, digest, implementation, read_lines, write_json
from benchmarks.metrics import evaluate, paired_bootstrap
from benchmarks.run import IsolatedRetrieval, load_schemas
from benchmarks.score import aggregate


class SavedResponse:
    def __init__(self, calls: list[Row]) -> None:
        self.saved = calls
        self.calls: list[Row] = []

    async def complete(self, request: StructuredRequest) -> Completion:
        if len(self.calls) >= len(self.saved):
            raise RuntimeError("Replay requested an unrecorded model call")
        call = self.saved[len(self.calls)]
        if (
            json.loads(request.prompt) != json.loads(call["prompt"])
            or request.system != call["system"]
            or request.schema != call["schema"]
        ):
            raise RuntimeError("Replay request differs from the saved gateway request")
        self.calls.append(call)
        if "error" in call:
            raise ModelFailure("Saved gateway call failed")
        return Completion(call["response"], Usage(**call["usage"]))


async def compare(bundle: Path, protocol: Row, output: Path) -> Row:
    source_protocol = json.loads((bundle / "protocol.json").read_text())
    for name, expected in source_protocol["artifacts_sha256"].items():
        if digest(bundle / name) != expected:
            raise ValueError(f"Frozen artifact changed: {name}")
    schemas = load_schemas(bundle / "catalog.json", set(source_protocol["withheld_category_ids"]))
    retrieval = CatalogRetrieval(schemas, ())
    sample = read_lines(bundle / "sample.jsonl")
    profiles = json.loads((bundle / "profiles.json").read_text())
    weights = json.loads((bundle / "weights.json").read_text())
    policies = {
        row["name"]: RuleRoutingPolicy(
            min_coverage=row["min_coverage"],
            min_category_score=protocol["common"]["min_category_score"],
            min_category_margin=protocol["common"]["min_category_margin"],
            min_supported_fields=protocol["common"]["min_supported_fields"],
            require_covered_text=row.get("require_covered_text", False),
        )
        for row in protocol["policies"]
    }
    predictions: dict[str, dict[int, Row]] = {name: {} for name in ("baseline", *policies)}
    decisions: dict[str, Counter[str]] = {name: Counter() for name in policies}
    saved_hashes = {}
    for row in sample:
        saved_path = bundle / "results" / f"hybrid-{row['sku_id']}.json"
        saved_hashes[saved_path.name] = digest(saved_path)
        saved = json.loads(saved_path.read_text())
        card = CardInput(
            title=row["title"],
            description=row["description"] or "",
            seller_params=tuple(SellerParam(**p) for p in row["seller_params"] or []),
            category_id=None,
        )
        for name, rows in predictions.items():
            model = SavedResponse(saved["calls"])
            policy = policies.get(name)
            isolated = IsolatedRetrieval(retrieval, schemas)
            service = StandAttributeFlow(
                AttributeFlow(model, FlowConfig(timeout_s=source_protocol["timeout_s"]), policy),
                isolated,
            )
            if policy:
                prepared = await service.prepare(card)
                decisions[name][route_rules(prepared, policy).reason] += 1
            started = time.perf_counter()
            prediction: Row = {"sku_id": row["sku_id"], "mode": name}
            try:
                result = await service.execute(card)
                prediction["result"] = asdict(result)
                prediction["evidence_exact"] = all(
                    result.text[a.start : a.end] == a.quote
                    for a in (*result.extraction.items, *result.extraction.extra_fields)
                    if a.status == "supported"
                )
            except ModelFailure as exc:
                prediction["error"] = type(exc).__name__
            prediction["replay_local_ms"] = 1000 * (time.perf_counter() - started)
            prediction["wall_ms"] = prediction["replay_local_ms"] + sum(
                c["wall_ms"] for c in model.calls
            )
            prediction["calls"] = model.calls
            prediction["retrieved_category_ids"] = [c.category_id for c in isolated.retrieved]
            rows[row["sku_id"]] = prediction
    results = {
        name: aggregate(sample, rows, profiles, weights) for name, rows in predictions.items()
    }
    comparisons = {}
    for name in policies:
        paired = []
        for row in sample:
            metrics = {}
            for label, mode in (("rules", "baseline"), ("hybrid", name)):
                counts = evaluate(row, predictions[mode][row["sku_id"]], profiles)[0].metrics()
                metrics[label] = {k: counts[k] for k in ("tp", "fp", "fn", "filled", "slots")}
            paired.append({"stratum": row["stratum"], **metrics})
        baseline, routed = results["baseline"], results[name]
        comparisons[name] = {
            "routing_decisions": dict(decisions[name]),
            "saved_calls": baseline["model_calls"] - routed["model_calls"],
            "saved_call_share": 1 - routed["model_calls"] / baseline["model_calls"],
            "delta_f1": routed["normalized"]["f1"] - baseline["normalized"]["f1"],
            "bootstrap": paired_bootstrap(paired, source_protocol["seed"]),
        }
        selected = [r for r in sample if not predictions[name][r["sku_id"]]["calls"]]
        comparisons[name]["selected_cards"] = len(selected)
        comparisons[name]["selected_before"] = (
            aggregate(selected, predictions["baseline"], profiles, weights) if selected else None
        )
        comparisons[name]["selected_after"] = (
            aggregate(selected, predictions[name], profiles, weights) if selected else None
        )
        comparisons[name]["unscored_values_change"] = (
            routed["unscored_predicted_values"] - baseline["unscored_predicted_values"]
        )
        comparisons[name]["changed_extractions"] = sum(
            predictions[name][r["sku_id"]].get("result", {}).get("extraction")
            != predictions["baseline"][r["sku_id"]].get("result", {}).get("extraction")
            for r in sample
        )
    report = {
        "protocol": protocol,
        "source_protocol_sha256": digest(bundle / "protocol.json"),
        "implementation_sha256": implementation(),
        "saved_response_sha256": saved_hashes,
        "results": results,
        "comparisons": comparisons,
        "external_calls_executed": 0,
        "latency_method": protocol["latency"],
        "limits": [
            "Previously used sample; exploratory comparison, not an independent test",
            "Cached responses are reused only after exact request matching",
            "Category scores are retrieval scores, not calibrated probabilities",
        ],
    }
    write_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    with threadpool_limits(limits=2):
        report = asyncio.run(compare(args.bundle, protocol, args.output))
    print(
        json.dumps(
            {
                name: {
                    "f1": r["normalized"]["f1"],
                    "calls": r["model_calls"],
                    "latency_ms": r["latency_ms"],
                }
                for name, r in report["results"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
