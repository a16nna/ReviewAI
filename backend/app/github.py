"""GitHub OAuth + PR review + webhook.

Tokens exist only in server memory (Fernet-encrypted) and are never sent to the browser or logged.
All state-changing endpoints require a CSRF token tied to the session.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode
import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import ai, analysis
from .db import SessionLocal, WebhookDelivery, get_db
from .ratelimit import limiter
from .reviews import review_out, save_review
from .schemas import MAX_CODE, Finding

log = logging.getLogger("reviewai.github")
router = APIRouter(prefix="/github", tags=["github"])
API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
OAUTH_BASE = os.environ.get("GITHUB_OAUTH_URL", "https://github.com").rstrip("/")  # override for GitHub Enterprise
NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
}
SESSION_TTL = 8 * 3600
MAX_FILES, MAX_FILE_BYTES, CONTEXT_RADIUS = 20, 200_000, 15
# Generate a stable key with: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
_KEY = os.environ.get("SESSION_KEY")
FERNET = Fernet(_KEY.encode() if _KEY else Fernet.generate_key())


@dataclass
class Session_:
    token_enc: bytes
    csrf: str
    created: float


SESSIONS: dict[str, Session_] = {}


def create_session(token: str) -> tuple[str, str]:
    now = time.time()
    for k in [k for k, s in SESSIONS.items() if now - s.created > SESSION_TTL]:
        SESSIONS.pop(k, None)
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    SESSIONS[sid] = Session_(FERNET.encrypt(token.encode()), csrf, now)
    return sid, csrf


def _eq(a: str, b: str) -> bool:
    """Constant-time comparison that cannot raise on non-ASCII input."""
    return hmac.compare_digest(a.encode("utf-8", "replace"), b.encode("utf-8", "replace"))


def _secure() -> bool:
    return os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def configured() -> bool:
    return bool(os.environ.get("GITHUB_CLIENT_ID") and os.environ.get("GITHUB_CLIENT_SECRET"))


def webhook_configured() -> bool:
    return bool(os.environ.get("GITHUB_WEBHOOK_SECRET"))


def gh(method: str, path: str, token: str, **kw):
    try:
        r = httpx.request(
            method,
            API + path,
            timeout=20,
            **kw,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    except httpx.HTTPError:
        raise HTTPException(502, "GitHub is unreachable") from None
    if r.status_code == 401:
        raise HTTPException(401, "GitHub token invalid or expired; reconnect")
    if r.status_code == 403:
        raise HTTPException(403, "GitHub denied the request (missing permission, SSO, or rate limit)")
    if r.status_code == 404:
        raise HTTPException(404, "Not found on GitHub, or this account/token cannot access it")
    if r.status_code == 422:
        raise HTTPException(422, "GitHub rejected the request")
    if r.status_code >= 400:
        raise HTTPException(502, f"GitHub error {r.status_code}")
    return r.json()


def get_session(reviewai_session: str | None = Cookie(None)) -> Session_:
    s = SESSIONS.get(reviewai_session or "")
    if not s or time.time() - s.created > SESSION_TTL:
        SESSIONS.pop(reviewai_session or "", None)
        raise HTTPException(401, "Not connected to GitHub")
    return s


def token_dep(s: Session_ = Depends(get_session)) -> str:
    return FERNET.decrypt(s.token_enc).decode()


def csrf_dep(request: Request, s: Session_ = Depends(get_session)) -> None:
    if not _eq(request.headers.get("x-csrf-token", ""), s.csrf):
        raise HTTPException(403, "Missing or invalid CSRF token")


def repo_dep(owner: str, repo: str) -> tuple[str, str]:
    if not (NAME.match(owner) and NAME.match(repo)):
        raise HTTPException(422, "Invalid repository name")
    return owner, repo


def parse_patch(patch: str) -> tuple[list[tuple[int, str]], set[int]]:
    """Return (added lines as (new line no, text), all new-side line numbers visible in the diff)."""
    added, visible, ln, in_hunk = [], set(), 0, False
    lines = patch.split("\n")
    if lines and lines[-1] == "":  # a trailing newline is not a diff line
        lines.pop()
    for line in lines:
        line = line.rstrip("\r")
        if line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            ln, in_hunk = (int(m.group(1)) if m else 0), True
        elif not in_hunk:
            continue  # anything before the first hunk header is not file content
        elif line.startswith("+"):
            added.append((ln, line[1:]))
            visible.add(ln)
            ln += 1
        elif line.startswith(("-", "\\")):
            continue
        else:
            visible.add(ln)
            ln += 1
    return added, visible


def added_lines(patch: str) -> list[tuple[int, str]]:
    return parse_patch(patch)[0]


@router.get("/status")
def status(response: Response, reviewai_session: str | None = Cookie(None)):
    s = SESSIONS.get(reviewai_session or "")
    login = None
    if s and time.time() - s.created <= SESSION_TTL:
        # Re-issue the readable CSRF cookie so the UI recovers if it was cleared.
        response.set_cookie("csrf_token", s.csrf, httponly=False, samesite="lax", secure=_secure(), max_age=SESSION_TTL)
        try:
            login = gh("GET", "/user", FERNET.decrypt(s.token_enc).decode()).get("login")
        except HTTPException:
            login = None
    return {
        "configured": configured(),
        "connected": bool(login),
        "login": login,
        "scope": os.environ.get("GITHUB_SCOPE", "public_repo"),
        "webhook_configured": webhook_configured(),
    }


@router.get("/login")
def login(response: Response):
    if not configured():
        raise HTTPException(503, "GitHub OAuth is not configured (set GITHUB_CLIENT_ID/GITHUB_CLIENT_SECRET)")
    state = secrets.token_urlsafe(24)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", secure=_secure(), max_age=600)
    q = urlencode(
        {
            "client_id": os.environ["GITHUB_CLIENT_ID"],
            "state": state,
            "scope": os.environ.get("GITHUB_SCOPE", "public_repo"),
            "redirect_uri": os.environ.get("GITHUB_REDIRECT_URI", "http://localhost:5173/api/github/callback"),
        }
    )
    return {"url": f"{OAUTH_BASE}/login/oauth/authorize?{q}"}


@router.get("/callback")
def callback(code: str, state: str, oauth_state: str | None = Cookie(None)):
    if not oauth_state or not _eq(oauth_state, state):
        raise HTTPException(400, "Invalid OAuth state")
    try:
        r = httpx.post(
            f"{OAUTH_BASE}/login/oauth/access_token",
            timeout=20,
            headers={"Accept": "application/json"},
            data={
                "client_id": os.environ.get("GITHUB_CLIENT_ID", ""),
                "client_secret": os.environ.get("GITHUB_CLIENT_SECRET", ""),
                "code": code,
            },
        )
        tok = r.json().get("access_token")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "GitHub token exchange failed") from None
    if not tok:
        raise HTTPException(400, "GitHub did not return a token")
    sid, csrf = create_session(tok)
    resp = RedirectResponse(os.environ.get("FRONTEND_URL", "http://localhost:5173") + "/settings")
    resp.set_cookie("reviewai_session", sid, httponly=True, samesite="lax", secure=_secure(), max_age=SESSION_TTL)
    resp.set_cookie("csrf_token", csrf, httponly=False, samesite="lax", secure=_secure(), max_age=SESSION_TTL)
    resp.delete_cookie("oauth_state")
    return resp


@router.post("/logout", status_code=204, dependencies=[Depends(csrf_dep)])
def logout(response: Response, reviewai_session: str | None = Cookie(None)):
    SESSIONS.pop(reviewai_session or "", None)
    response.delete_cookie("reviewai_session")
    response.delete_cookie("csrf_token")


@router.get("/repos")
def repos(tok: str = Depends(token_dep)):
    data = gh("GET", "/user/repos", tok, params={"per_page": 50, "sort": "updated"})
    return [{"full_name": r["full_name"], "private": r["private"], "default_branch": r["default_branch"]} for r in data]


@router.get("/repos/{owner}/{repo}/branches")
def branches(rp=Depends(repo_dep), tok: str = Depends(token_dep)):
    data = gh("GET", f"/repos/{rp[0]}/{rp[1]}/branches", tok, params={"per_page": 100})
    return [{"name": b["name"], "protected": b.get("protected", False)} for b in data]


@router.get("/repos/{owner}/{repo}/pulls")
def pulls(base: str | None = None, rp=Depends(repo_dep), tok: str = Depends(token_dep)):
    params = {"state": "open", "per_page": 30, **({"base": base} if base else {})}
    data = gh("GET", f"/repos/{rp[0]}/{rp[1]}/pulls", tok, params=params)
    return [
        {
            "number": p["number"],
            "title": p["title"],
            "author": p["user"]["login"],
            "head_branch": p["head"]["ref"],
            "base_branch": p["base"]["ref"],
        }
        for p in data
    ]


@router.get("/repos/{owner}/{repo}/pulls/{number}/files")
def pr_files(number: int, rp=Depends(repo_dep), tok: str = Depends(token_dep)):
    data = list_pr_files(f"/repos/{rp[0]}/{rp[1]}/pulls/{number}", tok)
    return [{"filename": f["filename"], "status": f["status"], "patch": f.get("patch")} for f in data]


def list_pr_files(base: str, tok: str) -> list[dict]:
    """All changed files of a PR (GitHub pages at 100; cap at 10 pages = 1000 files)."""
    out: list[dict] = []
    for page in range(1, 11):
        chunk = gh("GET", base + "/files", tok, params={"per_page": 100, "page": page})
        out += chunk
        if len(chunk) < 100:
            break
    return out


def build_context(lines: list[str], changed: set[int], radius: int = CONTEXT_RADIUS) -> tuple[str, dict[int, str]]:
    """Numbered excerpt: changed lines marked 'L<n>>', surrounding context 'L<n>:'."""
    keep: set[int] = set()
    for n in changed:
        keep.update(range(max(1, n - radius), min(len(lines), n + radius) + 1))
    rows, line_map, prev = [], {}, None
    for n in sorted(keep):
        if prev is not None and n != prev + 1:
            rows.append("...")
        rows.append(f"L{n}{'>' if n in changed else ':'} {lines[n - 1]}")
        line_map[n] = lines[n - 1]
        prev = n
    return "\n".join(rows)[:MAX_CODE], line_map


def _file_content(owner: str, repo: str, path: str, sha: str, tok: str) -> str | None:
    try:
        d = gh("GET", f"/repos/{owner}/{repo}/contents/{quote(path)}", tok, params={"ref": sha})
        if d.get("encoding") != "base64" or d.get("size", 0) > MAX_FILE_BYTES:
            return None
        return base64.b64decode(d["content"]).decode("utf-8")
    except (HTTPException, UnicodeDecodeError, KeyError, ValueError):
        return None


def run_pr_review(db: Session, owner: str, repo: str, number: int, tok: str, source_kind: str = "github_pr") -> dict:
    base = f"/repos/{owner}/{repo}/pulls/{number}"
    head_sha = gh("GET", base, tok)["head"]["sha"]
    files = list_pr_files(base, tok)
    provider, findings, skipped, ai_error = ai.get_provider(), [], [], None
    statuses: dict[str, str] = {}
    langs: set[str] = set()
    reviewed = 0
    for f in files:
        name, ext = f["filename"], os.path.splitext(f["filename"])[1].lower()
        added, _visible = parse_patch(f.get("patch") or "")
        if ext not in EXT:
            reason = "not a supported language"
        elif f["status"] == "removed":
            reason = "removed"
        elif not added:
            reason = "no added lines / patch unavailable"
        elif reviewed >= MAX_FILES:
            reason = f"over the {MAX_FILES}-file limit"
        else:
            reason = None
        if reason:
            skipped.append({"filename": name, "reason": reason})
            continue
        reviewed += 1
        lang, changed = EXT[ext], {n for n, _ in added}
        content = _file_content(owner, repo, name, head_sha, tok)
        if content is not None:
            lines = ai.split_lines(content)
            text, line_map = build_context(lines, changed)
            static, st = analysis.analyze(content, lang)
            for k, v in st.items():  # 'ran' wins; otherwise keep the first non-ran status
                statuses[k] = "ran" if v == "ran" or statuses.get(k) == "ran" else statuses.get(k, v)
            for s in static:
                if s.line_start in changed:
                    findings.append(s.model_copy(update={"file_path": name}))
        else:  # fall back to the added lines only (no surrounding context, no static analysis)
            line_map = dict(added)
            text = "\n".join(f"L{n}> {t}" for n, t in added)[:MAX_CODE]
            skipped.append({"filename": name, "reason": "full file unavailable; reviewed added lines only"})
        langs.add(lang)
        try:
            for x in ai.ground(provider.review(text, lang), line_map, changed):
                findings.append(Finding(**x.model_dump(exclude={"file_path"}), file_path=name, id="x", source="ai"))
        except ai.AIError as e:
            ai_error = str(e)
    review = save_review(
        db,
        language=next(iter(langs)) if len(langs) == 1 else "multi",
        provider=provider.name,
        is_mock=provider.is_mock,
        code_chars=0,
        analyzers=statuses,
        ai_error=ai_error,
        findings=findings,
        source_kind=source_kind,
        repo=f"{owner}/{repo}",
        pr_number=number,
        head_sha=head_sha,
    )
    out = review_out(review).model_dump(mode="json")
    return {**out, "review_id": review.id, "head_sha": head_sha, "files_reviewed": reviewed, "files_skipped": skipped}


@router.post("/repos/{owner}/{repo}/pulls/{number}/review", dependencies=[Depends(csrf_dep)])
def review_pr(
    number: int, rp=Depends(repo_dep), tok: str = Depends(token_dep), db: Session = Depends(get_db), _=Depends(limiter)
):
    return run_pr_review(db, rp[0], rp[1], number, tok)


class Comment(BaseModel):
    path: str = Field(max_length=500)
    line: int = Field(ge=1)
    body: str = Field(min_length=1, max_length=2000)


class PublishRequest(BaseModel):
    confirm: bool
    head_sha: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    comments: list[Comment] = Field(min_length=1, max_length=50)


@router.post("/repos/{owner}/{repo}/pulls/{number}/publish", dependencies=[Depends(csrf_dep)])
def publish(number: int, req: PublishRequest, rp=Depends(repo_dep), tok: str = Depends(token_dep)):
    if not req.confirm:
        raise HTTPException(400, "Explicit confirmation is required to publish comments")
    base = f"/repos/{rp[0]}/{rp[1]}/pulls/{number}"
    if not gh("GET", base, tok)["head"]["sha"].startswith(req.head_sha[:7]):
        raise HTTPException(409, "The pull request changed since the review; run the review again")
    visible = {f["filename"]: parse_patch(f.get("patch") or "")[1] for f in list_pr_files(base, tok)}
    bad = [f"{c.path}:{c.line}" for c in req.comments if c.line not in visible.get(c.path, set())]
    if bad:
        raise HTTPException(422, "These comments are not on lines of the pull-request diff: " + ", ".join(bad))
    body = {
        "commit_id": req.head_sha,
        "event": "COMMENT",
        "body": "ReviewAI comments (AI-assisted; verify before acting).",
        "comments": [
            {"path": c.path, "line": c.line, "side": "RIGHT", "body": "[ReviewAI] " + c.body.replace("@", "@\u200b")}
            for c in req.comments
        ],
    }
    gh("POST", base + "/reviews", tok, json=body)  # event=COMMENT only: never approves/merges/pushes
    return {"published": len(req.comments)}


def _process_webhook(owner: str, repo: str, number: int, token: str, delivery: str) -> None:
    outcome = "failed"
    with SessionLocal() as db:
        try:
            run_pr_review(db, owner, repo, number, token, source_kind="github_webhook")
            outcome = "done"
        except Exception as e:  # noqa: BLE001 - background task must not crash the worker
            log.warning("webhook review failed for %s/%s#%s: %s", owner, repo, number, type(e).__name__)
        row = db.get(WebhookDelivery, delivery)
        if row:
            row.status = outcome
            db.commit()


@router.post("/webhook", status_code=202)
async def webhook(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Webhook is not configured (set GITHUB_WEBHOOK_SECRET)")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > 1_000_000:
        raise HTTPException(413, "Payload too large")
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(413, "Payload too large")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not _eq(request.headers.get("x-hub-signature-256", ""), expected):
        raise HTTPException(401, "Invalid signature")
    event, delivery = request.headers.get("x-github-event", ""), request.headers.get("x-github-delivery", "")
    if event == "ping":
        return {"status": "pong"}
    if not delivery or len(delivery) > 100:
        raise HTTPException(400, "Missing delivery id")
    try:
        payload = json.loads(raw)
        action = payload.get("action")
        owner, repo = payload["repository"]["full_name"].split("/", 1)
        number = int(payload["pull_request"]["number"])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(400, "Malformed payload") from None
    if (
        event != "pull_request"
        or action not in ("opened", "synchronize", "reopened")
        or not (NAME.match(owner) and NAME.match(repo))
    ):
        return {"status": "ignored"}
    token = os.environ.get("GITHUB_WEBHOOK_TOKEN")
    db.add(WebhookDelivery(delivery_id=delivery, event=event, status="queued" if token else "no_token"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = db.get(WebhookDelivery, delivery)
        if prior and prior.status == "failed" and token:  # a redelivery of a failed run may retry
            prior.status = "queued"
            db.commit()
            background.add_task(_process_webhook, owner, repo, number, token, delivery)
            return {"status": "requeued"}
        return {"status": "duplicate"}
    if not token:
        return {"status": "recorded_but_not_reviewed", "reason": "GITHUB_WEBHOOK_TOKEN not set"}
    background.add_task(_process_webhook, owner, repo, number, token, delivery)
    return {"status": "queued"}
