import gzip
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from app.domain.card_text import SellerParam
from app.domain.lexicon import LexiconEntry
from app.domain.profile import AttributeProfile, Kind
from app.usecase.baseline_ports import RequiredRecord
from app.usecase.stand_ports import StandCategory, StandExample, StandPack, StandTwin

FORMAT = 1


class StandPackFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, pack: StandPack) -> int:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(encode(pack), ensure_ascii=False, separators=(",", ":"))
        data = gzip.compress(payload.encode("utf-8"), mtime=0)
        self._path.write_bytes(data)
        return len(data)

    def load(self) -> StandPack | None:
        if not self._path.is_file():
            return None
        raw = json.loads(gzip.decompress(self._path.read_bytes()).decode("utf-8"))
        return decode(raw)


class ParquetCategoryNames:
    def __init__(self, processed: Path) -> None:
        self._path = processed / "categories.parquet"

    def names(self) -> Mapping[int, tuple[str, str]]:
        table = pq.read_table(self._path, columns=["category_id", "name", "path"])
        return {c: (n or "", p or "") for c, n, p in zip(
            table["category_id"].to_pylist(), table["name"].to_pylist(),
            table["path"].to_pylist(), strict=True)}


def encode(pack: StandPack) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "built_at": pack.built_at,
        "threshold": pack.threshold,
        "profiles": [[p.name, p.kind.value, p.unit, list(p.keywords)]
                     for p in pack.profiles.values()],
        "entries": [[e.attribute, list(e.tokens), e.key, e.display] for e in pack.entries],
        "priors": [[c, a, values] for (c, a), values in pack.priors.items()],
        "required": [[r.category_id, r.attribute, r.weight] for r in pack.required],
        "categories": [[c.category_id, c.name, c.path] for c in pack.categories],
        "examples": [
            {"sku_id": e.sku_id, "category_id": e.category_id, "title": e.title,
             "description": e.description,
             "seller_params": [[p.name, p.value, p.unit] for p in e.seller_params]}
            for e in pack.examples
        ],
        "twins": [[t.sku_id, t.title, t.brand, t.model,
                   [[a, k, v] for a, (k, v) in t.values.items()]] for t in pack.twins],
    }


def decode(raw: dict[str, Any]) -> StandPack:
    if raw.get("format") != FORMAT:
        raise ValueError(f"unsupported stand pack format {raw.get('format')!r}")
    profiles = {n: AttributeProfile(n, Kind(k), u, tuple(w)) for n, k, u, w in raw["profiles"]}
    return StandPack(
        built_at=raw["built_at"],
        threshold=float(raw["threshold"]),
        profiles=profiles,
        entries=[LexiconEntry(a, tuple(t), k, d) for a, t, k, d in raw["entries"]],
        priors={(int(c), a): {k: float(v) for k, v in values.items()}
                for c, a, values in raw["priors"]},
        required=[RequiredRecord(int(c), a, float(w)) for c, a, w in raw["required"]],
        categories=[StandCategory(category_id=int(c), name=n, path=p)
                    for c, n, p in raw["categories"]],
        examples=[
            StandExample(sku_id=int(e["sku_id"]), category_id=int(e["category_id"]),
                         title=e["title"], description=e["description"],
                         seller_params=tuple(SellerParam(n, v, u)
                                             for n, v, u in e["seller_params"]))
            for e in raw["examples"]
        ],
        twins=tuple(StandTwin(sku_id=int(s), title=t, brand=b, model=m,
                              values={a: (k, v) for a, k, v in values})
                    for s, t, b, m, values in raw.get("twins", [])),
    )
