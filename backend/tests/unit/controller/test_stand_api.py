from pathlib import Path

from fastapi.testclient import TestClient

from app.adapter.dataset.stand_pack_file import StandPackFile
from app.domain.card_text import SellerParam
from app.domain.lexicon import LexiconEntry
from app.domain.profile import AttributeProfile, Kind
from app.main import create_app
from app.settings import Settings
from app.usecase.baseline_ports import RequiredRecord
from app.usecase.stand_ports import StandCategory, StandExample, StandPack

PHONE = 761
CARD = {"title": "Смартфон Samsung Galaxy", "description": "Корпус черного цвета",
        "seller_params": [{"name": "Цвет", "value": "черный"}], "category_id": PHONE}


def pack(threshold: float) -> StandPack:
    return StandPack(
        built_at="2026-10-14T12:00:00+00:00", threshold=threshold,
        profiles={"Бренд": AttributeProfile("Бренд", Kind.CATEGORICAL, "", ("бренд",)),
                  "Цвет": AttributeProfile("Цвет", Kind.CATEGORICAL, "", ("цвет",))},
        entries=[LexiconEntry("Бренд", ("samsung",), "samsung", "Samsung"),
                 LexiconEntry("Цвет", ("черный",), "черный", "черный")],
        priors={(PHONE, "Бренд"): {"samsung": 1.0}, (PHONE, "Цвет"): {"черный": 1.0}},
        required=[RequiredRecord(PHONE, "Бренд", 10.0), RequiredRecord(PHONE, "Цвет", 2.0)],
        categories=[StandCategory(category_id=PHONE, name="Смартфоны", path="Смартфоны")],
        examples=[StandExample(sku_id=7, category_id=PHONE, title="Смартфон Samsung",
                               description="Описание", seller_params=(SellerParam("Цвет", "черный"),))],
    )


def client(tmp_path: Path, threshold: float, save: bool = True) -> TestClient:
    path = tmp_path / "pack.json.gz"
    if save:
        StandPackFile(path).save(pack(threshold))
    return TestClient(create_app(Settings(stand_pack=str(path))))


def test_pack_round_trips_through_file(tmp_path: Path) -> None:
    path = tmp_path / "pack.json.gz"
    original = pack(0.35)

    StandPackFile(path).save(original)

    assert StandPackFile(path).load() == original
    assert StandPackFile(tmp_path / "missing.json.gz").load() is None


def test_stand_info_and_examples(tmp_path: Path) -> None:
    with client(tmp_path, 0.35) as http:
        info = http.get("/api/v1/stand").json()
        examples = http.get("/api/v1/examples").json()

    assert info["categories"][0]["attributes"] == ["Бренд", "Цвет"]
    assert examples["items"][0]["seller_params"] == [
        {"name": "Цвет", "value": "черный", "unit": None}]


def test_review_loop_over_http(tmp_path: Path) -> None:
    with client(tmp_path, 0.999) as http:
        first = http.post("/api/v1/extract", json=CARD).json()
        pending = next(v for v in first["values"] if v["attribute"] == "Бренд")
        queue = http.get("/api/v1/review", params={"status": "pending"}).json()["items"]
        resolved = http.post(f"/api/v1/review/{pending['review_id']}",
                             json={"action": "correct", "value": "Samsung Electronics"})
        twice = http.post(f"/api/v1/review/{pending['review_id']}", json={"action": "accept"})
        second = http.post("/api/v1/extract", json=CARD).json()

    assert pending["status"] == "review"
    assert pending["review_id"] in [i["id"] for i in queue]
    assert resolved.status_code == 200 and resolved.json()["status"] == "corrected"
    assert twice.status_code == 409 and twice.json()["code"] == "review_already_resolved"
    brand = next(v for v in second["values"] if v["attribute"] == "Бренд")
    assert (brand["status"], brand["value"], brand["source"]) == ("accepted",
                                                                  "Samsung Electronics", "review")


def test_errors_use_the_envelope(tmp_path: Path) -> None:
    with client(tmp_path, 0.35) as http:
        unknown = http.post("/api/v1/extract", json={**CARD, "category_id": 1})
        missing = http.post("/api/v1/review/nope", json={"action": "accept"})
        empty = http.post("/api/v1/extract", json={**CARD, "title": ""})
    with client(tmp_path / "none", 0.35, save=False) as http:
        unavailable = http.get("/api/v1/stand")

    assert (unknown.status_code, unknown.json()["code"]) == (422, "unknown_category")
    assert (missing.status_code, missing.json()["code"]) == (404, "review_item_not_found")
    assert (empty.status_code, empty.json()["code"]) == (422, "validation_error")
    assert (unavailable.status_code, unavailable.json()["code"]) == (503, "stand_unavailable")
