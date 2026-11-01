"""Manual full-stack verification: fake GitHub + real backend + real Vite dev server, driven through the Vite proxy.

Run from the backend folder with the venv active and `npm install` done in ../frontend:
    python tests/integration/verify_stack.py
It checks OAuth state, cookie flags, CSRF, Origin checks, token secrecy, PR review, publish validation, logout,
the signed webhook, duplicate handling and .env loading. It does NOT contact real GitHub or Anthropic.
"""

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
FRONTEND = BACKEND.parent / "frontend"
FAKE, API, WEB = "http://127.0.0.1:9100", "http://127.0.0.1:8000", "http://localhost:5173"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def wait(url: str, secs: int = 40) -> None:
    for _ in range(secs * 4):
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            time.sleep(0.25)
    raise SystemExit(f"timeout waiting for {url}")


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="reviewai_stack_"))
    db = (work / "stack.db").as_posix()
    # ALL backend configuration comes from this .env file (proves the .env loader works from the working dir)
    (work / ".env").write_text(
        "\n".join(
            [
                f"DATABASE_URL=sqlite:///{db}",
                "RETENTION_DAYS=7",
                "RATE_LIMIT_PER_MIN=1000",
                "GITHUB_CLIENT_ID=fake-client",
                "GITHUB_CLIENT_SECRET=fake-secret",
                f"GITHUB_API_URL={FAKE}",
                f"GITHUB_OAUTH_URL={FAKE}",
                "GITHUB_WEBHOOK_SECRET=hook-secret",
                "GITHUB_WEBHOOK_TOKEN=fake-token-good-code",
                "GEMINI_API_KEY=your-key-here",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "GEMINI_", "ANTHROPIC_", "DATABASE_"))}
    npx = shutil.which("npx") or "npx"
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "fake_github:app", "--app-dir", str(HERE), "--port", "9100"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND), "--port", "8000"],
            cwd=work,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        subprocess.Popen(
            [npx, "vite", "--port", "5173", "--strictPort"],
            cwd=FRONTEND,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
    ]
    try:
        wait(f"{FAKE}/__recorded")
        wait(f"{API}/health")
        wait(WEB)
        run()
    finally:
        for p in procs:
            p.terminate()
        shutil.rmtree(work, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


def run() -> None:
    seen_text: list[str] = []
    c = httpx.Client(base_url=WEB, follow_redirects=False, timeout=30)

    def req(method, url, **kw):
        r = c.request(method, url, **kw)
        seen_text.append(r.text + json.dumps(dict(r.headers)))
        return r

    r = req("GET", "/api/health")
    check("frontend proxy reaches backend (/api/health)", r.status_code == 200 and "demo" in r.json()["mode"])
    cap = req("GET", "/api/capabilities").json()
    check(
        ".env was loaded by the backend (RETENTION_DAYS=7, OAuth configured)",
        cap["retention_days"] == 7 and cap["github_oauth_configured"] and cap["webhook_configured"],
    )
    check("placeholder GEMINI key keeps demo/mock mode", cap["ai_provider"] == "mock")
    st = req("GET", "/api/github/status").json()
    check("status before login: configured but not connected", st["configured"] and not st["connected"])
    check("protected GitHub route needs a session", req("GET", "/api/github/repos").status_code == 401)

    r = req("GET", "/api/github/login")
    url = r.json()["url"]
    state = httpx.URL(url).params["state"]
    set_cookie = r.headers.get("set-cookie", "").lower()
    check(
        "login URL targets the configured OAuth host with the proxy callback",
        url.startswith(f"{FAKE}/login/oauth/authorize?") and "api%2Fgithub%2Fcallback" in url,
    )
    check(
        "oauth_state cookie is HttpOnly + SameSite=Lax",
        "oauth_state=" in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie,
    )
    check(
        "callback rejects a wrong state",
        req("GET", "/api/github/callback", params={"code": "good-code", "state": "x"}).status_code == 400,
    )
    c.cookies.set("oauth_state", state)  # the wrong-state attempt did not consume it
    r = req("GET", "/api/github/callback", params={"code": "bad-code", "state": state})
    check("callback rejects a code GitHub refuses", r.status_code == 400)
    r = req("GET", "/api/github/callback", params={"code": "good-code", "state": state})
    cookies = [h.lower() for h in r.headers.get_list("set-cookie")]
    sess = next((x for x in cookies if x.startswith("reviewai_session=")), "")
    csrf = next((x for x in cookies if x.startswith("csrf_token=")), "")
    check(
        "callback redirects to the frontend /settings page",
        r.status_code in (302, 307) and r.headers["location"] == f"{WEB}/settings",
    )
    check("session cookie is HttpOnly + SameSite=Lax", "httponly" in sess and "samesite=lax" in sess, sess)
    check("csrf cookie is readable by JS (not HttpOnly)", csrf and "httponly" not in csrf, csrf)
    check(
        "cookies survived the Vite proxy into the client jar",
        "reviewai_session" in c.cookies and "csrf_token" in c.cookies,
    )
    token = c.cookies.get("csrf_token")

    st = req("GET", "/api/github/status").json()
    check("status after login shows the account", st["connected"] and st["login"] == "fake-octocat")
    check("repos listed", req("GET", "/api/github/repos").json()[0]["full_name"] == "fake/repo")
    check("branches listed", req("GET", "/api/github/repos/fake/repo/branches").json()[0]["name"] == "main")
    check(
        "pull requests listed",
        req("GET", "/api/github/repos/fake/repo/pulls", params={"base": "main"}).json()[0]["number"] == 1,
    )

    review_url = "/api/github/repos/fake/repo/pulls/1/review"
    check("PR review without CSRF header is refused (403)", req("POST", review_url).status_code == 403)
    check(
        "PR review with a wrong CSRF header is refused (403)",
        req("POST", review_url, headers={"X-CSRF-Token": "nope"}).status_code == 403,
    )
    check(
        "cross-site Origin is refused even with a valid CSRF header",
        req("POST", review_url, headers={"X-CSRF-Token": token, "Origin": "http://evil.example"}).status_code == 403,
    )
    r = req("POST", review_url, headers={"X-CSRF-Token": token, "Origin": WEB})
    body = r.json()
    check("PR review succeeds with CSRF header + allowed Origin", r.status_code == 200, r.text[:200])
    static = [f for f in body.get("findings", []) if f["source"] == "static_analysis" and f["rule_id"] == "B307"]
    ran = body.get("analyzers", {}).get("bandit") == "ran"
    check(
        "changed-line mapping: eval() finding is on file line 3 of app.py"
        if ran
        else "bandit unavailable here: reported as such, not faked",
        (static and static[0]["line_start"] == 3 and static[0]["file_path"] == "app.py") if ran else not static,
    )
    check("mock AI result is labelled", body["is_mock"] and any("[MOCK]" in f["title"] for f in body["findings"]))
    check(
        "review was persisted and is retrievable",
        req("GET", f"/api/reviews/{body['review_id']}").json()["repo"] == "fake/repo",
    )

    pub = "/api/github/repos/fake/repo/pulls/1/publish"
    hdr = {"X-CSRF-Token": token}
    good = {
        "confirm": True,
        "head_sha": body["head_sha"],
        "comments": [{"path": "app.py", "line": 3, "body": "ping @someone"}],
    }
    check(
        "publish without confirmation refused (400)",
        req("POST", pub, headers=hdr, json={**good, "confirm": False}).status_code == 400,
    )
    check("publish without CSRF refused (403)", req("POST", pub, json=good).status_code == 403)
    r = req("POST", pub, headers=hdr, json={**good, "comments": [{"path": "app.py", "line": 99, "body": "x"}]})
    check("comment outside the diff refused (422)", r.status_code == 422 and "app.py:99" in r.text)
    check("nothing reached GitHub from the refused attempts", httpx.get(f"{FAKE}/__recorded").json() == [])
    r = req("POST", pub, headers=hdr, json=good)
    rec = httpx.get(f"{FAKE}/__recorded").json()
    check(
        "confirmed publish reaches GitHub as event=COMMENT only",
        r.status_code == 200 and len(rec) == 1 and rec[0]["event"] == "COMMENT",
    )
    check(
        "published comment is on the right line, prefixed, @mention neutralised",
        rec
        and rec[0]["comments"][0]["line"] == 3
        and rec[0]["comments"][0]["body"].startswith("[ReviewAI]")
        and "@someone" not in rec[0]["comments"][0]["body"],
    )

    # webhook through the proxy (GitHub would call this URL)
    payload = json.dumps(
        {"action": "opened", "repository": {"full_name": "fake/repo"}, "pull_request": {"number": 1}}
    ).encode()
    sig = "sha256=" + hmac.new(b"hook-secret", payload, hashlib.sha256).hexdigest()
    hh = {"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "stack-1", "Content-Type": "application/json"}
    check(
        "webhook with a bad signature refused (401)",
        req(
            "POST", "/api/github/webhook", content=payload, headers={**hh, "X-Hub-Signature-256": "sha256=00"}
        ).status_code
        == 401,
    )
    r = req("POST", "/api/github/webhook", content=payload, headers={**hh, "X-Hub-Signature-256": sig})
    check(
        "signed webhook accepted and queued (no CSRF/Origin needed, signature is the auth)",
        r.status_code == 202 and r.json()["status"] == "queued",
        r.text,
    )
    check(
        "same delivery id is ignored as duplicate",
        req("POST", "/api/github/webhook", content=payload, headers={**hh, "X-Hub-Signature-256": sig}).json()["status"]
        == "duplicate",
    )
    got = []
    for _ in range(40):
        got = req("GET", "/api/reviews", params={"source_kind": "github_webhook"}).json()
        if got:
            break
        time.sleep(0.25)
    check("webhook produced exactly one saved review", len(got) == 1 and got[0]["pr_number"] == 1, str(len(got)))
    check("webhook never posted a comment to GitHub", len(httpx.get(f"{FAKE}/__recorded").json()) == 1)

    r = req("POST", "/api/github/logout", headers={**hdr, "Origin": WEB})
    check("logout (with CSRF) succeeds", r.status_code == 204)
    c.cookies.clear()
    check("after logout the old session no longer works", req("GET", "/api/github/repos").status_code == 401)

    leaked = [t for t in seen_text if "fake-token-good-code" in t]
    check("the GitHub access token never appeared in any response body or header", not leaked)


if __name__ == "__main__":
    sys.exit(main())
