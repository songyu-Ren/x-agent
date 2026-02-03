from fastapi.testclient import TestClient

from app.main import app


def test_metrics_endpoint_exposes_prometheus() -> None:
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    body = resp.text
    assert "http_requests_total" in body
