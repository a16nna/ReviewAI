import uuid
from sqlalchemy.orm import Session
from .db import FindingRow, Review
from .schemas import Finding, ReviewOut


def save_review(db: Session, *, language: str, provider: str, is_mock: bool, code_chars: int,
                analyzers: dict, ai_error: str | None, findings: list[Finding],
                source_kind: str = "manual", repo: str | None = None, pr_number: int | None = None,
                head_sha: str | None = None) -> Review:
    r = Review(id=uuid.uuid4().hex, language=language, provider=provider, is_mock=is_mock,
               code_chars=code_chars, analyzers=analyzers, ai_error=ai_error, source_kind=source_kind,
               repo=repo, pr_number=pr_number, head_sha=head_sha)
    for seq, f in enumerate(findings):
        d = f.model_dump(exclude={"id"})
        r.items.append(FindingRow(seq=seq, finding_key=f"{f.analyzer or f.source}-{seq}", **d))
    db.add(r)
    db.commit()
    return r


def finding_out(row: FindingRow) -> Finding:
    return Finding(
        id=row.finding_key, source=row.source, analyzer=row.analyzer, rule_id=row.rule_id,
        category=row.category, severity=row.severity, title=row.title, description=row.description,
        impact=row.impact or "", file_path=row.file_path, line_start=row.line_start,
        line_end=row.line_end, remediation=row.remediation or "", corrected_code=row.corrected_code,
        confidence=row.confidence, certainty=row.certainty, evidence=row.evidence)


def review_out(r: Review) -> ReviewOut:
    return ReviewOut(id=r.id, created_at=r.created_at, language=r.language, provider=r.provider,
                     is_mock=r.is_mock, analyzers=r.analyzers, ai_error=r.ai_error,
                     source_kind=r.source_kind, repo=r.repo, pr_number=r.pr_number,
                     findings=[finding_out(i) for i in r.items])
