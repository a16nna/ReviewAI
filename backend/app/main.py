import logging
import os
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session
from . import ai, analysis, github
from .db import FindingRow, Review, get_db, purge_old
from .ratelimit import limiter
from .reviews import finding_out, review_out, save_review
from .schemas import Finding, ReviewOut, ReviewRequest

log = logging.getLogger("reviewai")
app = FastAPI(title="ReviewAI", version="0.2.0")
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def origin_check(request: Request, call_next):
    """CSRF defence in depth: browsers send Origin on cross-site writes; reject unknown origins."""
    origin = request.headers.get("origin")
    if (
        request.method in ("POST", "DELETE", "PUT", "PATCH")
        and origin
        and origin not in ORIGINS
        and request.url.path != "/github/webhook"
    ):
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    return await call_next(request)


def _get(db: Session, rid: str) -> Review:
    r = db.get(Review, rid)
    if not r:
        raise HTTPException(404, "Review not found")
    return r


@app.get("/health")
def health():
    state = ai.provider_status()["state"]
    return {"status": "ok", "mode": {"mock": "demo (mock AI)", "gemini": "live AI"}.get(state, "AI unavailable")}


@app.post("/reviews", response_model=ReviewOut, status_code=201)
def create_review(req: ReviewRequest, db: Session = Depends(get_db), _=Depends(limiter)):
    purge_old(db, int(os.environ.get("RETENTION_DAYS", "0")))
    static, analyzer_status = analysis.analyze(req.code, req.language)
    provider, ai_error, ai_findings = ai.get_provider(), None, []
    try:
        raw = provider.review(ai.number_lines(req.code), req.language)
        grounded = ai.ground(raw, {i: t for i, t in enumerate(ai.split_lines(req.code), 1)})
        ai_findings = [Finding(**f.model_dump(exclude={"file_path"}), id="x", source="ai") for f in grounded]
    except ai.AIError as e:
        ai_error = str(e)
    r = save_review(
        db,
        language=req.language,
        provider=provider.name,
        is_mock=provider.is_mock,
        code_chars=len(req.code),
        analyzers=analyzer_status,
        ai_error=ai_error,
        findings=ai_findings + static,
    )
    return review_out(r)


@app.get("/reviews", response_model=list[ReviewOut])
def list_reviews(
    language: str | None = None,
    q: str | None = None,
    severity: str | None = None,
    source_kind: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Review).order_by(Review.created_at.desc())
    if language:
        stmt = stmt.where(Review.language == language)
    if source_kind:
        stmt = stmt.where(Review.source_kind == source_kind)
    if severity:
        stmt = stmt.where(exists().where(and_(FindingRow.review_id == Review.id, FindingRow.severity == severity)))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Review.language).like(like),
                func.lower(func.coalesce(Review.repo, "")).like(like),
                exists().where(
                    and_(
                        FindingRow.review_id == Review.id,
                        or_(func.lower(FindingRow.title).like(like), func.lower(FindingRow.description).like(like)),
                    )
                ),
            )
        )
    return [review_out(r) for r in db.scalars(stmt.limit(limit).offset(offset))]


@app.get("/reviews/{rid}", response_model=ReviewOut)
def get_review(rid: str, db: Session = Depends(get_db)):
    return review_out(_get(db, rid))


@app.get("/reviews/{rid}/findings", response_model=list[Finding])
def get_findings(
    rid: str,
    severity: str | None = None,
    category: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
):
    _get(db, rid)
    stmt = select(FindingRow).where(FindingRow.review_id == rid).order_by(FindingRow.seq)
    for col, val in ((FindingRow.severity, severity), (FindingRow.category, category), (FindingRow.source, source)):
        if val:
            stmt = stmt.where(col == val)
    return [finding_out(x) for x in db.scalars(stmt)]


@app.delete("/reviews/{rid}", status_code=204)
def delete_review(rid: str, db: Session = Depends(get_db)):
    db.delete(_get(db, rid))
    db.commit()


@app.get("/reviews/{rid}/report")
def report(rid: str, format: str = Query("json", pattern="^(json|md)$"), db: Session = Depends(get_db)):
    out = review_out(_get(db, rid))
    if format == "json":
        return out
    lines = [
        f"# ReviewAI report {out.id}",
        f"- Language: {out.language}",
        f"- Provider: {out.provider}{' (MOCK - not real AI)' if out.is_mock else ''}",
        f"- Analyzers: {out.analyzers}",
    ]
    if out.repo:
        lines.append(f"- Pull request: {out.repo}#{out.pr_number}")
    lines += ["- Code was analyzed, never executed.", ""]
    for f in out.findings:
        loc = f" ({f.file_path + ':' if f.file_path else 'line '}{f.line_start})" if f.line_start else ""
        lines += [
            f"## [{f.severity}] {f.title}{loc}",
            f"Source: {f.source}{' / ' + f.analyzer if f.analyzer else ''}, "
            f"confidence: {f.confidence}, certainty: {f.certainty}",
            "",
            f.description,
            "",
        ]
        if f.remediation:
            lines += [f"**Fix:** {f.remediation}", ""]
        if f.corrected_code:
            lines += ["```", f.corrected_code, "```", ""]
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    real = ~and_(Review.is_mock.is_(True), FindingRow.source == "ai")  # mock placeholders aren't findings

    def counts(col):
        rows = db.execute(
            select(col, func.count()).join(Review, Review.id == FindingRow.review_id).where(real).group_by(col)
        ).all()
        return {k: v for k, v in rows}

    days = db.execute(
        select(func.date(Review.created_at), func.count())
        .group_by(func.date(Review.created_at))
        .order_by(func.date(Review.created_at))
    ).all()
    recent = db.scalars(select(Review).order_by(Review.created_at.desc()).limit(5)).all()
    return {
        "total_reviews": db.scalar(select(func.count()).select_from(Review)),
        "by_severity": counts(FindingRow.severity),
        "by_category": counts(FindingRow.category),
        "by_source": counts(FindingRow.source),
        "by_day": [{"date": d, "count": c} for d, c in days],
        "recent": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "language": r.language,
                "findings": len(r.items),
                "is_mock": r.is_mock,
                "source_kind": r.source_kind,
            }
            for r in recent
        ],
    }


@app.get("/capabilities")
def capabilities():
    return {
        "ai_provider": ai.get_provider().name,
        "ai": ai.provider_status(),
        "github_oauth_configured": github.configured(),
        "webhook_configured": github.webhook_configured(),
        "retention_days": int(os.environ.get("RETENTION_DAYS", "0")),
        "languages": analysis.availability(),
    }


app.include_router(github.router)
