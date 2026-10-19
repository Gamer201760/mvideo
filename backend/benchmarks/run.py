import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from threadpoolctl import threadpool_limits

from app.adapter.llm.gateway import GatewayModel
from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.card_text import SellerParam, match_form
from app.domain.errors import ModelFailure
from app.domain.inference import Completion, StructuredRequest
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.interface import LanguageModel
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput
from benchmarks.files import ROOT, Row, digest, implementation, read_lines, write_json


class IsolatedRetrieval:
    def __init__(self, retrieval: CatalogRetrieval, schemas: dict[int, CatalogCandidate]) -> None:
        self.retrieval = retrieval
        self.schemas = schemas
        self.retrieved: tuple[CatalogCandidate, ...] = ()

    def retrieve(self, text: str, k: int = 3) -> tuple[CatalogCandidate, ...]:
        self.retrieved = self.retrieval.retrieve(text, k)
        return self.retrieved

    def remember(self, category: CatalogCandidate, title: str) -> None:
        return None

    def snapshot(self) -> tuple[CatalogCandidate, ...]:
        return tuple(self.schemas.values())

    def added_categories(self) -> tuple[CatalogCandidate, ...]:
        return ()

    def add_category(
        self,
        path: str,
        fields: tuple[CatalogField, ...],
        title: str,
    ) -> CatalogCandidate:
        path = " / ".join(p.strip() for p in path.split("/") if p.strip())
        if not path or len(path) > 200 or not fields:
            raise ValueError("new category requires a path and supported fields")
        for schema in self.schemas.values():
            if match_form(schema.path).strip() == match_form(path).strip():
                return schema
        return CatalogCandidate(-1, path, 0, fields)


class RecordedModel:
    def __init__(self, delegate: LanguageModel, mode: str) -> None:
        self.delegate = delegate
        self.mode = mode
        self.calls: list[Row] = []

    async def complete(self, request: StructuredRequest) -> Completion:
        if self.mode == "model":
            payload = json.loads(request.prompt)
            for card in payload["c"]:
                card.pop("h", None)
            request = replace(
                request, prompt=json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            )
        record: Row = {"system": request.system, "prompt": request.prompt, "schema": request.schema}
        self.calls.append(record)
        started = time.perf_counter()
        try:
            result = await self.delegate.complete(request)
            record.update({"response": result.output, "usage": asdict(result.usage)})
            return result
        except (ModelFailure, TimeoutError, TypeError, ValueError) as exc:
            record["error"] = str(exc) if isinstance(exc, ModelFailure) else type(exc).__name__
            raise
        finally:
            record["wall_ms"] = 1000 * (time.perf_counter() - started)


def load_schemas(path: Path, withheld: set[int]) -> dict[int, CatalogCandidate]:
    return {
        row["category_id"]: CatalogCandidate(
            row["category_id"],
            row["path"],
            0,
            tuple(
                CatalogField(
                    f["attribute"],
                    f["kind"],
                    f["unit"],
                    tuple(f["values"]),
                    tuple(f["aliases"]),
                )
                for f in row["fields"]
            ),
        )
        for row in json.loads(path.read_text())
        if row["category_id"] not in withheld
    }


def environment(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    return {**values, **os.environ}


async def execute(args: argparse.Namespace, protocol: Row) -> None:
    schemas = load_schemas(args.bundle / "catalog.json", set(protocol["withheld_category_ids"]))
    with threadpool_limits(limits=2):
        retrieval = CatalogRetrieval(schemas, ())
    env = environment(args.env_file)
    gateway = None
    if any(mode != "rules" for mode in args.modes):
        if not args.execute_gateway:
            raise ValueError("External inference requires --execute-gateway")
        if not env.get("GATEWAY_API_KEY"):
            raise ValueError("GATEWAY_API_KEY is missing")
        gateway = GatewayModel(
            env.get("GATEWAY_URL", "https://ai.goatwhistle.ru/v1"),
            protocol["requested_model"],
            env["GATEWAY_API_KEY"],
            timeout_s=protocol["timeout_s"],
        )
    local = LocalRulesModel()
    semaphore = asyncio.Semaphore(protocol["concurrency"])
    sample = read_lines(args.bundle / "sample.jsonl")
    print(
        json.dumps(
            {
                "cards": len(sample),
                "modes": args.modes,
                "requested_model": protocol["requested_model"],
            }
        ),
        flush=True,
    )

    async def process(row: Row, mode: str) -> None:
        path = args.bundle / "results" / f"{mode}-{row['sku_id']}.json"
        if path.exists():
            return
        async with semaphore:
            delegate = local if mode == "rules" else gateway
            if delegate is None:
                raise ValueError("Gateway is not configured")
            model = RecordedModel(delegate, mode)
            isolated = IsolatedRetrieval(retrieval, schemas)
            flow = StandAttributeFlow(
                AttributeFlow(model, FlowConfig(concurrency=1, timeout_s=protocol["timeout_s"])),
                isolated,
            )
            card = CardInput(
                title=row["title"],
                description=row["description"] or "",
                seller_params=tuple(SellerParam(**p) for p in row["seller_params"] or []),
                category_id=None,
            )
            started = time.perf_counter()
            record: Row = {
                "sku_id": row["sku_id"],
                "mode": mode,
                "started_at": datetime.now(UTC).isoformat(),
            }
            try:
                result = await flow.execute(card)
                record["result"] = asdict(result)
                record["evidence_exact"] = all(
                    result.text[a.start : a.end] == a.quote
                    for a in (*result.extraction.items, *result.extraction.extra_fields)
                    if a.status == "supported"
                )
            except (ModelFailure, TimeoutError, TypeError, ValueError) as exc:
                record["error"] = str(exc) if isinstance(exc, ModelFailure) else type(exc).__name__
            record["wall_ms"] = 1000 * (time.perf_counter() - started)
            record["retrieved_category_ids"] = [c.category_id for c in isolated.retrieved]
            record["calls"] = model.calls
            write_json(path, record)
            print(
                json.dumps(
                    {
                        "sku_id": row["sku_id"],
                        "mode": mode,
                        "wall_ms": round(record["wall_ms"]),
                        "error": record.get("error"),
                        "reported_models": [
                            c["usage"]["model"] for c in model.calls if "usage" in c
                        ],
                    }
                ),
                flush=True,
            )

    tasks: list[asyncio.Task[None]] = []
    for row in sample:
        modes = args.modes if row["sku_id"] % 2 else list(reversed(args.modes))
        tasks.extend(asyncio.create_task(process(row, mode)) for mode in modes)
    try:
        with threadpool_limits(limits=2):
            await asyncio.gather(*tasks)
    finally:
        if gateway is not None:
            await gateway.aclose()
        write_json(
            args.bundle / "run-status.json",
            {
                "finished_at": datetime.now(UTC).isoformat(),
                "implementation_unchanged": implementation() == protocol["implementation_sha256"],
                "result_files": len(list((args.bundle / "results").glob("*.json"))),
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--modes", nargs="+", choices=("rules", "model", "hybrid"), default=["rules"]
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--execute-gateway", action="store_true")
    args = parser.parse_args()
    protocol = json.loads((args.bundle / "protocol.json").read_text())
    if implementation() != protocol["implementation_sha256"]:
        parser.error("Implementation differs from the frozen protocol; prepare a new bundle")
    for name, expected in protocol["artifacts_sha256"].items():
        if digest(args.bundle / name) != expected:
            parser.error(f"Frozen artifact changed: {name}")
    asyncio.run(execute(args, protocol))


if __name__ == "__main__":
    main()
