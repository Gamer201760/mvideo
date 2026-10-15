from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_health_reports_liveness() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_lists_health() -> None:
    with TestClient(create_app(Settings())) as client:
        schema = client.get("/openapi.json").json()

    assert "/api/v1/health" in schema["paths"]
