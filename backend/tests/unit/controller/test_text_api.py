from pathlib import Path

from fastapi.testclient import TestClient

from app.adapter.dataset.stand_pack_file import StandPackFile
from app.adapter.dataset.text_index_files import TextIndexFiles
from app.adapter.embeddings.catalog_search import TFIDF_KIND
from app.adapter.ranker.isotonic import IsotonicCalibrator
from app.domain.lexicon import LexiconEntry
from app.domain.profile import AttributeProfile, Kind
from app.main import create_app
from app.settings import Settings
from app.usecase.baseline_ports import RequiredRecord
from app.usecase.stand_ports import StandCategory, StandPack
from app.usecase.text_ports import CatalogEntry

PHONE = 761
IRON = 469
PAGE = ("<html><nav>Каталог</nav><h1>Смартфон Samsung Galaxy A55</h1>"
        "<p>Корпус&nbsp;черного цвета.</p></html>")


def pack() -> StandPack:
    return StandPack(
        built_at="2026-10-15T12:00:00+00:00", threshold=0.35,
        profiles={"Бренд": AttributeProfile("Бренд", Kind.CATEGORICAL, "", ("бренд",)),
                  "Цвет": AttributeProfile("Цвет", Kind.CATEGORICAL, "", ("цвет",))},
        entries=[LexiconEntry("Бренд", ("samsung",), "samsung", "Samsung"),
                 LexiconEntry("Цвет", ("черный",), "черный", "черный")],
        priors={(PHONE, "Бренд"): {"samsung": 1.0}, (PHONE, "Цвет"): {"черный": 1.0}},
        required=[RequiredRecord(PHONE, "Бренд", 10.0), RequiredRecord(PHONE, "Цвет", 2.0)],
        categories=[StandCategory(category_id=PHONE, name="Смартфоны", path="Смартфоны")],
        examples=[],
    )


def build_index(directory: Path) -> None:
    files = TextIndexFiles(directory)
    entries = [CatalogEntry(1, PHONE, "смартфон samsung galaxy a35", {}),
               CatalogEntry(2, PHONE, "смартфон samsung galaxy s24", {}),
               CatalogEntry(3, IRON, "утюг philips gc1740", {})]
    files.start(entries, {PHONE: "Смартфоны", IRON: "Утюги"}, "none", 2)
    files.add_vectors([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    files.finish()
    calibrator = IsotonicCalibrator()
    calibrator.fit([0.2, 0.5, 0.9, 1.0], [False, False, True, True])
    files.save_model(TFIDF_KIND, calibrator, 0.5, {})


def client(tmp_path: Path, index: bool = True) -> TestClient:
    path = tmp_path / "pack.json.gz"
    StandPackFile(path).save(pack())
    if index:
        build_index(tmp_path / "text")
    settings = Settings(stand_pack=str(path), stand_models=str(tmp_path / "models"),
                        text_index=str(tmp_path / "text"))
    return TestClient(create_app(settings))


def test_plain_page_returns_category_title_and_quoted_values(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.post("/api/v1/extract-text", json={"text": PAGE})

    assert response.status_code == 200
    body = response.json()
    assert body["category_id"] == PHONE
    assert body["category_name"] == "Смартфоны"
    assert body["search"] == TFIDF_KIND
    assert body["title"]["value"] == "Смартфон Samsung Galaxy A55"
    values = {v["attribute"]: v for v in body["values"]}
    assert values["Цвет"]["value"] == "черный"
    brand = values["Бренд"]
    assert PAGE[brand["start"]:brand["end"]] == "Samsung"


def test_missing_index_is_reported_as_unavailable(tmp_path: Path) -> None:
    with client(tmp_path, index=False) as api:
        response = api.post("/api/v1/extract-text", json={"text": PAGE})

    assert response.status_code == 503
    assert response.json()["code"] == "text_index_missing"


def test_text_without_product_content_is_unprocessable(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.post("/api/v1/extract-text", json={"text": "<script>x()</script>"})

    assert response.status_code == 422
    assert response.json()["code"] == "empty_text"
