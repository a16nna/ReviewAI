"""Gemini provider tests. A fake client replaces the SDK, so no API key or network is needed."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import ai
from app.main import app
from tests.test_ai_and_ground import fake

c = TestClient(app)
CODE = "import os\nx = eval(input())\n"


def reply(*findings):
    return json.dumps({"findings": list(findings)})


def item(**kw):
    base = dict(category="Security", severity="High", title="Use of eval", description="eval runs user input",
                impact="RCE", line_start=2, line_end=2, remediation="Use ast.literal_eval",
                confidence="high", certainty="confirmed", evidence="x = eval(input())")
    base.update(kw)
    return base


# ---- request shape ---------------------------------------------------------------------------------
def test_request_asks_for_structured_json_with_configured_model():
    p, seen = fake(reply())
    p.review(ai.number_lines(CODE), "python")
    cfg = seen["config"]
    assert seen["model"] == "test-model"
    assert cfg["response_mime_type"] == "application/json" and cfg["response_schema"] is ai.RESPONSE_SCHEMA
    assert "evidence" in ai.RESPONSE_SCHEMA["properties"]["findings"]["items"]["required"]


# ---- validation ------------------------------------------------------------------------------------
def test_valid_finding_is_returned_and_evidence_is_mandatory():
    p, _ = fake(reply(item(), item(title="No evidence", evidence="")))
    out = p.review(ai.number_lines(CODE), "python")
    assert [f.title for f in out] == ["Use of eval"]


@pytest.mark.parametrize("bad", ["not json", "[]", '{"findings":"x"}', '{"findings":[{"severity":"Nope"}]}'])
def test_invalid_model_output_raises_sanitized_error(bad):
    with pytest.raises(ai.AIError, match="malformed"):
        fake(bad)[0].review("x", "python")


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_response(text):
    with pytest.raises(ai.AIError, match="empty"):
        fake(text)[0].review("x", "python")


def test_blocked_prompt_is_reported():
    with pytest.raises(ai.AIError, match="blocked"):
        fake("{}", block="SAFETY")[0].review("x", "python")


def test_truncated_output_is_reported():
    with pytest.raises(ai.AIError, match="truncated"):
        fake('{"findings":[', finish="FinishReason.MAX_TOKENS")[0].review("x", "python")


# ---- line numbers are never invented ------------------------------------------------------------------
def test_invented_line_numbers_are_removed_by_grounding():
    p, _ = fake(reply(item(line_start=57, line_end=60)))
    raw = p.review(ai.number_lines(CODE), "python")
    g = ai.ground(raw, {i: t for i, t in enumerate(ai.split_lines(CODE), 1)})[0]
    assert g.line_start == 2 and g.evidence == "x = eval(input())"  # re-anchored by unique evidence
    p, _ = fake(reply(item(line_start=57, line_end=60, evidence="def totally_made_up():")))
    g = ai.ground(p.review(ai.number_lines(CODE), "python"), {1: "import os", 2: "x = eval(input())"})[0]
    assert g.line_start is None and g.evidence is None and g.confidence == "low"


# ---- failure mapping -----------------------------------------------------------------------------------
def api_error(code, status="", msg="boom sk-SECRET-123"):
    e = type("ClientError", (Exception,), {})(msg)
    e.code, e.status = code, status
    return e


@pytest.mark.parametrize("exc,expected", [
    (api_error(400, "INVALID_ARGUMENT", "API key not valid. sk-SECRET-123"), "API key"),
    (api_error(401, "UNAUTHENTICATED"), "API key"),
    (api_error(403, "PERMISSION_DENIED"), "API key"),
    (api_error(429, "RESOURCE_EXHAUSTED", "Quota exceeded for metric"), "quota exhausted"),
    (api_error(429, "RESOURCE_EXHAUSTED", "Too many requests"), "rate limit"),
    (api_error(404, "NOT_FOUND"), "GEMINI_MODEL"),
    (api_error(504, "DEADLINE_EXCEEDED"), "timed out"),
    (api_error(503, "UNAVAILABLE"), "unavailable"),
    (type("ReadTimeout", (Exception,), {})("t"), "timed out"),
    (type("ConnectError", (Exception,), {})("dns"), "network"),
    (ConnectionError("down"), "network"),
])
def test_provider_failures_are_mapped_and_secrets_never_leak(exc, expected):
    with pytest.raises(ai.AIError, match=expected) as e:
        fake(exc=exc)[0].review("x", "python")
    assert "SECRET" not in str(e.value)


# ---- configuration -------------------------------------------------------------------------------------------
def test_missing_key_gives_mock_with_clear_message(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert isinstance(ai.get_provider(), ai.MockProvider)
    st = ai.provider_status()
    assert st["state"] == "mock" and "GEMINI_API_KEY" in st["message"]
    assert "No GEMINI_API_KEY" in ai.MockProvider().review("x", "python")[0].description


def test_placeholder_key_counts_as_unset(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "your-key-here")
    assert isinstance(ai.get_provider(), ai.MockProvider)


def test_key_with_working_sdk_selects_gemini_and_model_is_configurable(monkeypatch):
    class FakeClient:
        def __init__(self, **kw):
            self.kw = kw
    import sys, types
    genai = types.ModuleType("google.genai")
    genai.Client = FakeClient
    gtypes = types.ModuleType("google.genai.types")
    gtypes.HttpOptions = lambda **kw: SimpleNamespace(**kw)
    google = types.ModuleType("google")
    google.genai = genai
    genai.types = gtypes
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", gtypes)
    monkeypatch.setenv("GEMINI_API_KEY", "real-looking-key")
    monkeypatch.setenv("GEMINI_MODEL", "my-model")
    p = ai.get_provider()
    assert isinstance(p, ai.GeminiProvider) and p.model == "my-model"
    st = ai.provider_status()
    assert st["state"] == "gemini" and st["model"] == "my-model" and "real-looking-key" not in json.dumps(st)
    monkeypatch.delenv("GEMINI_MODEL")
    assert ai.get_provider().model == ai.DEFAULT_GEMINI_MODEL


def test_sdk_import_failure_reports_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "real-looking-key")
    class NoSdk:
        def __init__(self, *a, **k):
            raise ImportError("google-genai missing")
    monkeypatch.setattr(ai, "GeminiProvider", NoSdk)
    st = ai.provider_status()
    assert st["state"] == "unavailable" and "google-genai" in st["message"]
    with pytest.raises(ai.AIError, match="google-genai"):
        ai.get_provider().review("x", "python")


# ---- API integration: stored, static results kept separate, key never exposed ---------------------------------------
class StubGemini:
    name, is_mock = "gemini", False

    def review(self, code, language):
        return fake(reply(item()))[0].review(code, language)


def test_gemini_findings_are_stored_and_static_findings_stay_separate(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    monkeypatch.setattr(ai, "get_provider", lambda: StubGemini())
    body = c.post("/reviews", json={"code": CODE, "language": "python"}).json()
    by_source = {}
    for f in body["findings"]:
        by_source.setdefault(f["source"], []).append(f)
    gem = by_source["ai"][0]
    assert body["provider"] == "gemini" and body["is_mock"] is False and body["ai_error"] is None
    assert (gem["title"], gem["line_start"], gem["evidence"], gem["severity"]) == ("Use of eval", 2, "x = eval(input())", "High")
    assert {f["analyzer"] for f in by_source["static_analysis"]} <= {"ruff", "bandit"} and by_source["static_analysis"]
    stored = c.get(f"/reviews/{body['id']}/findings", params={"source": "ai"}).json()
    assert len(stored) == 1 and stored[0]["evidence"] == "x = eval(input())"
    assert any(r["id"] == body["id"] and r["provider"] == "gemini" for r in c.get("/reviews").json())
    assert c.get("/stats").json()["by_source"]["ai"] >= 1


def test_provider_failure_keeps_static_results_and_shows_message(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    p, _ = fake(exc=api_error(429, "RESOURCE_EXHAUSTED", "Quota exceeded"))
    monkeypatch.setattr(ai, "get_provider", lambda: p)
    body = c.post("/reviews", json={"code": CODE, "language": "python"}).json()
    assert "quota" in body["ai_error"] and any(f["source"] == "static_analysis" for f in body["findings"])


def test_capabilities_and_health_never_expose_the_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "real-looking-key-ZZZ")
    monkeypatch.setattr(ai, "get_provider", lambda: ai.UnavailableProvider("down"))
    for path in ("/capabilities", "/health"):
        r = c.get(path)
        assert "ZZZ" not in r.text
    assert c.get("/capabilities").json()["ai"]["state"] == "unavailable"
    assert c.get("/health").json()["mode"] == "AI unavailable"
