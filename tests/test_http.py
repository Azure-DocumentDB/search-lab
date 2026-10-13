from fastapi.testclient import TestClient

from search_lab.app import create_app
from search_lab.config import LabError

HEADERS = {"X-Search-Lab": "same-origin"}


class Stub:
    version = "unit-test-only"

    def close(self):
        pass

    def ready(self):
        raise LabError("Service unavailable; no fallback.")

    def search(self, text, filters, k):
        return {"text": text, "filters": filters, "k": k}

    def evaluate_case(self, id, k, repeats):
        return {"id": id, "k": k, "repeats": repeats}


def client():
    return TestClient(create_app(Stub), base_url="http://localhost", client=("127.0.0.1", 50000))


def test_ui_and_safe_config_without_cloud():
    with client() as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "not confidence" in r.text
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
        assert len(c.get("/api/config").json()["queries"]) == 8
        assert c.get("/static/app.js").status_code == 200
        r = c.get("/api/status")
        assert r.status_code == 503
        assert "no fallback" in r.json()["detail"]


def test_origin_host_client_and_header():
    with client() as c:
        assert c.post("/api/search", json={"text": "rain"}).status_code == 403
        assert (
            c.post("/api/search", headers={**HEADERS, "Origin": "https://evil.test"}, json={"text": "rain"}).status_code
            == 403
        )
        assert c.get("/api/config", headers={"Host": "evil.test"}).status_code == 400
    with TestClient(create_app(Stub), base_url="http://localhost", client=("203.0.113.2", 1)) as c:
        assert c.get("/").status_code == 403


def test_payload_constraints_and_injection():
    with client() as c:
        for payload in [
            {"text": "rain", "category": {"$ne": None}},
            {"text": "rain", "k": 100},
            {"text": "rain", "index": "hnsw"},
            {"text": "rain", "pipeline": []},
            {"text": " "},
            {"text": "x" * 601},
        ]:
            assert c.post("/api/search", headers=HEADERS, json=payload).status_code == 422
        r = c.post("/api/search", headers=HEADERS, json={"text": "rain", "category": "outdoors"})
        assert r.json() == {"text": "rain", "filters": {"category": "outdoors"}, "k": 3}
        assert c.post("/api/evaluate-case", headers=HEADERS, json={"case_id": "q1", "repeats": 100}).status_code == 422


def test_provider_error_never_leaks():
    def fail():
        raise RuntimeError("api-key=SECRET mongodb+srv://SECRET")

    with TestClient(create_app(fail), base_url="http://localhost", client=("127.0.0.1", 1)) as c:
        response = c.post("/api/search", headers=HEADERS, json={"text": "rain"})
        assert response.status_code == 503
        assert "SECRET" not in response.text


def test_cloud_mode_requires_explicit_safe_configuration(monkeypatch):
    import pytest

    from search_lab.app import hosting

    monkeypatch.setenv("SEARCH_LAB_HOSTING", "appservice")
    with pytest.raises(LabError):
        hosting()
    monkeypatch.setenv("WEBSITE_HOSTNAME", "lab.azurewebsites.net")
    monkeypatch.setenv("SEARCH_LAB_IP_RESTRICTIONS_CONFIRMED", "true")
    monkeypatch.setenv("SEARCH_LAB_OPERATOR_IPS", "0.0.0.0/0")
    with pytest.raises(LabError):
        hosting()
    monkeypatch.setenv("SEARCH_LAB_OPERATOR_IPS", "203.0.113.3/32")
    assert hosting()[0] is True
    with TestClient(create_app(Stub), base_url="https://lab.azurewebsites.net", client=("10.0.0.3", 1)) as c:
        assert c.get("/api/config").status_code == 200
        assert (
            c.post("/api/search", headers={**HEADERS, "Origin": "https://evil.test"}, json={"text": "rain"}).status_code
            == 403
        )
        assert (
            c.post(
                "/api/search", headers={**HEADERS, "Origin": "https://lab.azurewebsites.net"}, json={"text": "rain"}
            ).status_code
            == 200
        )


def test_chunked_oversized_request_is_bounded():
    with client() as c:
        response = c.post(
            "/api/search",
            headers={**HEADERS, "Content-Type": "application/json"},
            content=iter([b'{"text":"', b"x" * 5000, b'"}']),
        )
        assert response.status_code == 413
