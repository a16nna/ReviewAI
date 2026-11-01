"""Move findings into their own table; add PR metadata and webhook delivery log."""
import json
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _legacy_rows():
    """Read and normalise old JSON findings before touching the schema (bad rows become empty)."""
    bind = op.get_bind()
    out = []
    for rid, raw in bind.execute(sa.text("SELECT id, findings FROM reviews WHERE findings IS NOT NULL")).fetchall():
        try:
            items = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except ValueError:
            items = []
        items = [f for f in items if isinstance(f, dict)] if isinstance(items, list) else []
        out.append((rid, items))
    return out


def upgrade():
    legacy = _legacy_rows()
    with op.batch_alter_table("reviews") as b:
        b.alter_column("findings", existing_type=sa.JSON, nullable=True)
        b.add_column(sa.Column("source_kind", sa.String, nullable=False, server_default="manual"))
        b.add_column(sa.Column("repo", sa.String, nullable=True))
        b.add_column(sa.Column("pr_number", sa.Integer, nullable=True))
        b.add_column(sa.Column("head_sha", sa.String, nullable=True))
        b.create_index("ix_reviews_source_kind", ["source_kind"])
    findings = op.create_table(
        "findings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("review_id", sa.String, sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("finding_key", sa.String, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("analyzer", sa.String, nullable=True),
        sa.Column("rule_id", sa.String, nullable=True),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("impact", sa.Text, nullable=False, server_default=""),
        sa.Column("file_path", sa.String, nullable=True),
        sa.Column("line_start", sa.Integer, nullable=True),
        sa.Column("line_end", sa.Integer, nullable=True),
        sa.Column("remediation", sa.Text, nullable=False, server_default=""),
        sa.Column("corrected_code", sa.Text, nullable=True),
        sa.Column("confidence", sa.String, nullable=False),
        sa.Column("certainty", sa.String, nullable=False, server_default="possible"),
    )
    op.create_index("ix_findings_review_id", "findings", ["review_id"])
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_index("ix_findings_category", "findings", ["category"])
    op.create_table(
        "webhook_deliveries",
        sa.Column("delivery_id", sa.String, primary_key=True),
        sa.Column("received_at", sa.DateTime, nullable=False),
        sa.Column("event", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
    )
    # Carry over records written by the old JSON-column design.
    for rid, items in legacy:
        for seq, f in enumerate(items):
            op.bulk_insert(findings, [{
                "review_id": rid, "seq": seq, "finding_key": f.get("id") or f"f-{seq}",
                "source": f.get("source") or "ai", "analyzer": None, "rule_id": None,
                "category": f.get("category") or "General", "severity": f.get("severity") or "Informational",
                "title": f.get("title") or "(untitled)", "description": f.get("description") or "",
                "impact": f.get("impact") or "", "file_path": f.get("file_path"),
                "line_start": f.get("line_start"), "line_end": f.get("line_end"),
                "remediation": f.get("remediation") or "", "corrected_code": f.get("corrected_code"),
                "confidence": f.get("confidence") or "medium", "certainty": "possible",
            }])
    op.get_bind().execute(sa.text("UPDATE reviews SET findings = NULL"))


def downgrade():
    raise RuntimeError("0002 is not reversible; restore from a backup instead")
