import base64
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import github
from app.main import app

SHA = "abc1234def5678"
PATCH = "@@ -0,0 +1,3 @@\n+import os\n+\n+x = eval(input())"
FILE = "import os\n\nx = eval(input())\n"


def client(csrf=True):
    sid, token = github.create_session("tok")
    c = TestClient(app)
    c.cookies.set("reviewai_session", sid)
    if csrf:
        c.headers["X-CSRF-Token"] = token
    return c


def fake_gh(calls=None, patch=PATCH, contents=True, head=SHA):
    def fake(method, path, tok, **kw):
        if calls is not None:
            calls.append((method, path, kw))
        if path == "/user":
            return {"login": "octocat"}
        if "/contents/" in path:
            if not contents:
                raise HTTPException(404, "nf")
            return {"encoding": "base64", "size": len(FILE), "content": base64.b64encode(FILE.encode()).decode()}
        if path.endswith("/files"):
            return [{"filename": "a.py", "status": "added", "patch": patch},
                    {"filename": "README.md", "status": "modified", "patch": "@@ -1 +1 @@\n+hi"}]
        if path.endswith("/reviews"):
            return {}
        if path.endswith("/branches"):
            return [{"name": "main", "protected": True}]
        return {"head": {"sha": head}}
    return fake


def test_added_lines_and_visible_lines():
    added, vis = github.parse_patch("@@ -1,3 +10,4 @@\n ctx\n-old\n+new1\n+new2\n ctx2")
    assert added == [(11, "new1"), (12, "new2")] and vis == {10, 11, 12, 13}


def test_not_connected_and_unconfigured():
    c2 = TestClient(app)
    assert c2.get("/github/status").json()["connected"] is False
    assert c2.get("/github/repos").status_code == 401
    assert c2.get("/github/login").status_code == 503


def test_callback_rejects_bad_state():
    assert TestClient(app).get("/github/callback?code=x&state=y").status_code == 400


def test_session_token_is_encrypted_in_memory():
    sid, _ = github.create_session("ghp_secret_token")
    assert b"ghp_secret_token" not in github.SESSIONS[sid].token_enc


def test_review_pr_is_context_aware_and_persisted(monkeypatch):
    monkeypatch.setattr(github, "gh", fake_gh())
    c = client()
    body = c.post("/github/repos/o/r/pulls/1/review").json()
    assert body["files_reviewed"] == 1 and body["is_mock"]
    assert {"filename": "README.md", "reason": "not a supported language"} in body["files_skipped"]
    static = [f for f in body["findings"] if f["source"] == "static_analysis"]
    b307 = [f for f in static if f["rule_id"] == "B307"]
    assert b307 and b307[0]["file_path"] == "a.py" and b307[0]["line_start"] == 3  # mapped to the real file line
    assert c.get(f"/reviews/{body['review_id']}").json()["repo"] == "o/r"


def test_review_pr_falls_back_when_full_file_unavailable(monkeypatch):
    monkeypatch.setattr(github, "gh", fake_gh(contents=False))
    body = client().post("/github/repos/o/r/pulls/1/review").json()
    assert any("added lines only" in s["reason"] for s in body["files_skipped"])
    assert body["files_reviewed"] == 1


def test_build_context_marks_changed_lines():
    text, lm = github.build_context([f"l{i}" for i in range(1, 60)], {30}, radius=2)
    assert "L30> l30" in text and "L29: l29" in text and "L10" not in text and set(lm) == {28, 29, 30, 31, 32}


def test_branches_listing(monkeypatch):
    monkeypatch.setattr(github, "gh", fake_gh())
    assert client().get("/github/repos/o/r/branches").json() == [{"name": "main", "protected": True}]


def test_state_changing_endpoints_require_csrf(monkeypatch):
    monkeypatch.setattr(github, "gh", fake_gh())
    c = client(csrf=False)
    req = {"confirm": True, "head_sha": SHA, "comments": [{"path": "a.py", "line": 3, "body": "x"}]}
    assert c.post("/github/repos/o/r/pulls/1/publish", json=req).status_code == 403
    assert c.post("/github/repos/o/r/pulls/1/review").status_code == 403
    assert c.post("/github/logout").status_code == 403


def test_publish_requires_auth():
    req = {"confirm": True, "head_sha": SHA, "comments": [{"path": "a", "line": 1, "body": "x"}]}
    assert TestClient(app).post("/github/repos/o/r/pulls/1/publish", json=req).status_code == 401


def test_publish_requires_confirmation_and_valid_repo(monkeypatch):
    calls = []
    monkeypatch.setattr(github, "gh", fake_gh(calls))
    c = client()
    req = {"confirm": False, "head_sha": SHA, "comments": [{"path": "a.py", "line": 3, "body": "x"}]}
    assert c.post("/github/repos/o/r/pulls/1/publish", json=req).status_code == 400
    assert calls == []
    assert c.post("/github/repos/a$b/r/pulls/1/publish", json={**req, "confirm": True}).status_code == 422


def test_publish_validates_positions_and_head(monkeypatch):
    calls = []
    monkeypatch.setattr(github, "gh", fake_gh(calls))
    c = client()
    ok = {"confirm": True, "head_sha": SHA, "comments": [{"path": "a.py", "line": 3, "body": "ping @octocat"}]}
    r = c.post("/github/repos/o/r/pulls/1/publish", json=ok)
    assert r.json() == {"published": 1}
    post = [x for x in calls if x[0] == "POST"][0]
    assert post[2]["json"]["event"] == "COMMENT" and "@octocat" not in post[2]["json"]["comments"][0]["body"]
    bad = {**ok, "comments": [{"path": "a.py", "line": 99, "body": "x"}, {"path": "zzz.py", "line": 1, "body": "x"}]}
    r = c.post("/github/repos/o/r/pulls/1/publish", json=bad)
    assert r.status_code == 422 and "a.py:99" in r.json()["detail"]
    monkeypatch.setattr(github, "gh", fake_gh(head="fff9999fff"))
    assert c.post("/github/repos/o/r/pulls/1/publish", json=ok).status_code == 409


def test_github_error_mapping(monkeypatch):
    import httpx
    c = client()
    for code, expected in ((403, 403), (404, 404), (500, 502)):
        monkeypatch.setattr(httpx, "request", lambda *a, _c=code, **k: SimpleNamespace(status_code=_c, json=lambda: {}))
        assert c.get("/github/repos").status_code == expected
    def boom(*a, **k):
        raise httpx.ConnectError("x")
    monkeypatch.setattr(httpx, "request", boom)
    assert c.get("/github/repos").status_code == 502


@pytest.fixture
def hook_env(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("GITHUB_WEBHOOK_TOKEN", "pat")


def signed(body: bytes, secret="s3cret"):
    import hashlib
    import hmac
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post_hook(body: dict, delivery="d1", event="pull_request", sig=None):
    import json
    raw = json.dumps(body).encode()
    return TestClient(app).post("/github/webhook", content=raw, headers={
        "X-Hub-Signature-256": sig or signed(raw), "X-GitHub-Event": event, "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json"})


PR = {"action": "opened", "repository": {"full_name": "o/r"}, "pull_request": {"number": 7}}


def test_webhook_unconfigured_and_bad_signature(monkeypatch, hook_env):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET")
    assert post_hook(PR).status_code == 503
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    assert post_hook(PR, sig="sha256=deadbeef").status_code == 401
    assert post_hook(PR, sig=signed(b"{}", "wrong")).status_code == 401


def test_webhook_ping_and_ignored_events(hook_env):
    assert post_hook({}, event="ping").json() == {"status": "pong"}
    assert post_hook({**PR, "action": "closed"}, delivery="d-closed").json() == {"status": "ignored"}


def test_webhook_processes_once_and_dedupes(monkeypatch, hook_env):
    monkeypatch.setattr(github, "gh", fake_gh())
    assert post_hook(PR, delivery="dup-1").json() == {"status": "queued"}
    assert post_hook(PR, delivery="dup-1").json() == {"status": "duplicate"}
    items = TestClient(app).get("/reviews?source_kind=github_webhook").json()
    assert len([r for r in items if r["pr_number"] == 7]) == 1


def test_webhook_never_publishes_comments(monkeypatch, hook_env):
    calls = []
    monkeypatch.setattr(github, "gh", fake_gh(calls))
    post_hook({**PR, "pull_request": {"number": 8}}, delivery="nopub-1")
    assert not [c for c in calls if c[0] == "POST"]


def test_webhook_rejects_malformed_payload(hook_env):
    assert post_hook({"action": "opened"}, delivery="bad-1").status_code == 400


# ---------- audit additions ----------
def test_parse_patch_edge_cases():
    # header without counts, "\ No newline" marker, blank context line, two hunks, CRLF content
    patch = ("@@ -1 +1,2 @@\n-old\n+new\n+tail\n\\ No newline at end of file\n"
             "@@ -10,3 +11,4 @@ def f():\n ctx\n\n+added\r\n ctx2")
    added, visible = github.parse_patch(patch)
    assert added == [(1, "new"), (2, "tail"), (13, "added")]          # \r stripped, numbering resets per hunk
    assert visible == {1, 2, 11, 12, 13, 14}                          # blank context line counted as line 12
    assert github.parse_patch("") == ([], set())
    assert github.parse_patch("@@ -0,0 +1,1 @@\n+x\n") == ([(1, "x")], {1})   # trailing newline: no phantom line 2
    assert github.parse_patch("stray header\n@@ -0,0 +1 @@\n+x") == ([(1, "x")], {1})


def test_parse_patch_does_not_split_on_form_feed_or_unicode_separators():
    added, _ = github.parse_patch("@@ -0,0 +1,3 @@\n+a\x0cb\n+c\u2028d\n+x = eval(1)")
    assert added[-1] == (3, "x = eval(1)")


def test_removed_lines_that_look_like_headers_do_not_shift_numbers():
    added, _ = github.parse_patch("@@ -1,3 +1,2 @@\n--- removed sql comment\n ctx\n+++ added plus plus\n")
    assert added == [(2, "++ added plus plus")]


def test_all_pages_of_changed_files_are_fetched(monkeypatch):
    pages = []

    def fake(method, path, tok, **kw):
        pages.append(kw["params"]["page"])
        n = 100 if kw["params"]["page"] == 1 else 1
        return [{"filename": f"f{kw['params']['page']}_{i}.txt", "status": "added", "patch": ""} for i in range(n)]
    monkeypatch.setattr(github, "gh", fake)
    assert len(github.list_pr_files("/repos/o/r/pulls/1", "tok")) == 101 and pages == [1, 2]


def test_publish_accepts_files_beyond_the_first_page(monkeypatch):
    def fake(method, path, tok, **kw):
        if path.endswith("/files"):
            if kw["params"]["page"] == 1:
                return [{"filename": f"d{i}.md", "status": "added", "patch": ""} for i in range(100)]
            return [{"filename": "late.py", "status": "added", "patch": PATCH}]
        return {"head": {"sha": SHA}}
    monkeypatch.setattr(github, "gh", fake)
    req = {"confirm": True, "head_sha": SHA, "comments": [{"path": "late.py", "line": 2, "body": "x"}]}
    assert client().post("/github/repos/o/r/pulls/1/publish", json=req).json() == {"published": 1}


def test_non_ascii_secrets_are_rejected_not_crashed(monkeypatch, hook_env):
    monkeypatch.setattr(github, "gh", fake_gh())
    c = client(csrf=False)
    raw = "é-not-the-token".encode("latin-1")  # raw non-ASCII header bytes, as a hostile client could send
    assert c.post("/github/logout", headers={"X-CSRF-Token": raw}).status_code == 403
    oc = TestClient(app)
    oc.cookies.set("oauth_state", "e")
    assert oc.get("/github/callback", params={"code": "x", "state": "é"}).status_code == 400
    import json
    body = json.dumps(PR).encode()
    r = TestClient(app).post("/github/webhook", content=body, headers={
        "X-Hub-Signature-256": "sha256=é".encode("latin-1"), "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "ascii-1"})
    assert r.status_code == 401


def test_status_reissues_csrf_cookie_for_a_valid_session(monkeypatch):
    monkeypatch.setattr(github, "gh", fake_gh())
    sid, csrf = github.create_session("tok")
    c = TestClient(app)
    c.cookies.set("reviewai_session", sid)  # note: no csrf_token cookie present
    r = c.get("/github/status")
    assert r.json()["login"] == "octocat" and r.cookies.get("csrf_token") == csrf
    assert "csrf_token" not in TestClient(app).get("/github/status").cookies  # nothing for anonymous users


def test_webhook_failed_run_can_be_retried_but_successful_one_cannot(monkeypatch, hook_env):
    from app.db import SessionLocal, WebhookDelivery

    def state():
        with SessionLocal() as s:
            return s.get(WebhookDelivery, "retry-1").status

    def boom(*a, **k):
        raise HTTPException(502, "github down")
    monkeypatch.setattr(github, "gh", boom)
    assert post_hook(PR, delivery="retry-1").json() == {"status": "queued"}
    assert state() == "failed"
    monkeypatch.setattr(github, "gh", fake_gh())
    assert post_hook(PR, delivery="retry-1").json() == {"status": "requeued"}
    assert state() == "done"
    assert post_hook(PR, delivery="retry-1").json() == {"status": "duplicate"}


def test_webhook_rejects_oversized_payload_before_reading_it(hook_env):
    r = TestClient(app).post("/github/webhook", content=b"x" * 1_000_001, headers={
        "X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "big-1", "X-Hub-Signature-256": "sha256=00"})
    assert r.status_code == 413


def test_webhook_signature_covers_the_exact_body(hook_env):
    import json
    raw = json.dumps(PR).encode()
    good = signed(raw)
    r = TestClient(app).post("/github/webhook", content=raw + b" ", headers={
        "X-Hub-Signature-256": good, "X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "tamper-1"})
    assert r.status_code == 401  # body modified after signing
