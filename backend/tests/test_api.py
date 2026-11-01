import os
import tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/t.db"
os.environ.pop("GEMINI_API_KEY", None)
from fastapi.testclient import TestClient  # noqa: E402
from app import ai  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import AIFinding  # noqa: E402

c = TestClient(app)
BAD = "import os\nx = eval(input())\n"


def test_health_demo_mode():
    assert "mock" in c.get("/health").json()["mode"]


def test_validation():
    assert c.post("/reviews", json={"code": "", "language": "python"}).status_code == 422
    assert c.post("/reviews", json={"code": "  \n", "language": "python"}).status_code == 422
    assert c.post("/reviews", json={"code": "x", "language": "cobol"}).status_code == 422
    assert c.post("/reviews", json={"code": "a" * 100_001, "language": "python"}).status_code == 422


def test_review_persist_report_delete():
    r = c.post("/reviews", json={"code": BAD, "language": "python"})
    assert r.status_code == 201
    body = r.json()
    assert body["is_mock"] is True
    srcs = {f["source"] for f in body["findings"]}
    assert "static_analysis" in srcs and any("B307" in f["title"] for f in body["findings"])
    assert c.get(f"/reviews/{body['id']}").status_code == 200
    assert any(x["id"] == body["id"] for x in c.get("/reviews").json())
    md = c.get(f"/reviews/{body['id']}/report?format=md")
    assert "MOCK" in md.text and "never executed" in md.text
    assert c.delete(f"/reviews/{body['id']}").status_code == 204
    assert c.get(f"/reviews/{body['id']}").status_code == 404


def test_analyzer_status_is_reported_honestly():
    body = c.post("/reviews", json={"code": "int main(){}", "language": "cpp"}).json()
    assert body["analyzers"]["cppcheck"] == "ran" or body["analyzers"]["cppcheck"].startswith("unavailable")


def test_ai_failure_keeps_static_results(monkeypatch):
    class Boom:
        name, is_mock = "gemini", False
        def review(self, code, language):
            raise ai.AIError("timeout")
    monkeypatch.setattr(ai, "get_provider", lambda: Boom())
    body = c.post("/reviews", json={"code": BAD, "language": "python"}).json()
    assert body["ai_error"] and body["findings"]


def test_ai_output_parsing_rejects_malformed():
    from app.schemas import AIResult
    import pytest
    with pytest.raises(ValueError):
        AIResult.model_validate_json('{"findings":[{"severity":"Nope"}]}')
    assert AIFinding(category="x", severity="Low", title="t", description="d")


def test_default_origins_include_localhost_and_loopback_ip():
    body = {"code": "x=1", "language": "python"}
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        assert c.post("/reviews", json=body, headers={"Origin": origin}).status_code == 201
    assert c.post("/reviews", json=body, headers={"Origin": "http://localhost:6666"}).status_code == 403


def test_form_feed_in_source_does_not_shift_reported_lines():
    code = "# a\x0cb\nimport os\nx = eval(input())\n"
    body = c.post("/reviews", json={"code": code, "language": "python"}).json()
    assert [f["line_start"] for f in body["findings"] if f["rule_id"] == "B307"] == [3]
