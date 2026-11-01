import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, delete, event, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./reviewai.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _fk_pragma(dbapi_conn, _):
    if DATABASE_URL.startswith("sqlite"):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Review(Base):
    """Metadata + findings only. Submitted source code is NOT persisted."""

    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=now)
    language: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String)
    is_mock: Mapped[bool] = mapped_column(Boolean)
    code_chars: Mapped[int] = mapped_column(Integer)
    analyzers: Mapped[dict] = mapped_column(JSON)
    ai_error: Mapped[str | None] = mapped_column(String, nullable=True)
    legacy_findings: Mapped[list | None] = mapped_column("findings", JSON, nullable=True)  # deprecated
    source_kind: Mapped[str] = mapped_column(String, default="manual", index=True)
    repo: Mapped[str | None] = mapped_column(String, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    items: Mapped[list["FindingRow"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", passive_deletes=True, order_by="FindingRow.seq"
    )


class FindingRow(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    finding_key: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    analyzer: Mapped[str | None] = mapped_column(String, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remediation: Mapped[str] = mapped_column(Text, default="")
    corrected_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String)
    certainty: Mapped[str] = mapped_column(String, default="possible")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # verified verbatim code line(s)
    review: Mapped[Review] = relationship(back_populates="items")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    delivery_id: Mapped[str] = mapped_column(String, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    event: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)


def init_db(url: str | None = None) -> None:
    """Apply Alembic migrations; adopt pre-Alembic databases by stamping them at the initial revision.

    Before migrating an *existing* SQLite file, a timestamped copy is written next to it
    (``<db>.bak-<UTC time>``) because SQLite DDL is not fully transactional.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    url = url or DATABASE_URL
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    eng = create_engine(url)
    try:
        tables = inspect(eng).get_table_names()
        with eng.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
        db_file = eng.url.database if eng.url.get_backend_name() == "sqlite" else None
    finally:
        eng.dispose()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if "reviews" in tables and current != head and db_file and Path(db_file).is_file():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(db_file, f"{db_file}.bak-{stamp}")
    if "reviews" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "0001")
    command.upgrade(cfg, "head")


def purge_old(db, days: int) -> int:
    """Data retention: delete reviews older than `days` (0 disables)."""
    if days <= 0:
        return 0
    cutoff = now() - timedelta(days=days)
    n = db.execute(delete(Review).where(Review.created_at < cutoff)).rowcount
    db.execute(delete(WebhookDelivery).where(WebhookDelivery.received_at < cutoff))
    db.commit()
    return n


init_db()


def get_db():
    with SessionLocal() as s:
        yield s
