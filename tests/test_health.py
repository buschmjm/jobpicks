"""API endpoint tests."""

from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_hello() -> None:
    response = client.get("/api/hello")
    assert response.status_code == 200
    assert response.json() == {"message": "hello from job-platform"}


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
