import json
import sqlite3
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from app import db as appdb
from app.main import app

c = TestClient(app)


def test_legacy_json_database_is_migrated(tmp_path):
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE reviews (id VARCHAR PRIMARY KEY, created_at DATETIME NOT NULL, language VARCHAR NOT NULL,"
                " provider VARCHAR NOT NULL, is_mock BOOLEAN NOT NULL, code_chars INTEGER NOT NULL,"
                " analyzers JSON NOT NULL, ai_error VARCHAR, findings JSON NOT NULL)")
    old = [{"id": "ruff-0", "category": "Maintainability", "severity": "Low", "title": "F401", "description": "unused",
            "impact": "", "line_start": 1, "line_end": 1, "remediation": "", "confidence": "high",
            "source": "static_analysis"}]
    con.execute("INSERT INTO reviews VALUES ('old1','2026-01-01 00:00:00','python','mock',1,10,'{}',NULL,?)",
                (json.dumps(old),))
    con.commit()
    con.close()
    appdb.init_db(f"sqlite:///{path}")
    con = sqlite3.connect(path)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003"
    assert len(list(tmp_path.glob("legacy.db.bak-*"))) == 1
    assert con.execute("SELECT review_id, title, severity, source FROM findings").fetchall() == \
        [("old1", "F401", "Low", "static_analysis")]
    assert con.execute("SELECT findings, source_kind FROM reviews").fetchone() == (None, "manual")
    con.close()
    appdb.init_db(f"sqlite:///{path}")  # idempotent


def test_fresh_database_gets_full_schema(tmp_path):
    appdb.init_db(f"sqlite:///{tmp_path / 'fresh.db'}")
    names = {r[0] for r in sqlite3.connect(tmp_path / "fresh.db").execute("SELECT name FROM sqlite_master")}
    assert {"reviews", "findings", "webhook_deliveries", "ix_findings_severity"} <= names


def test_delete_cascades_to_findings():
    rid = c.post("/reviews", json={"code": "x = eval(input())\n", "language": "python"}).json()["id"]
    def count():
        with appdb.SessionLocal() as s:
            q = select(func.count()).select_from(appdb.FindingRow).where(appdb.FindingRow.review_id == rid)
            return s.scalar(q)
    assert count() > 0
    assert c.delete(f"/reviews/{rid}").status_code == 204
    assert count() == 0


def test_source_code_is_not_stored():
    secret = "SUPER_UNIQUE_SOURCE_MARKER_123"
    rid = c.post("/reviews", json={"code": f"{secret} = eval(input())\n", "language": "python"}).json()["id"]
    con = sqlite3.connect(appdb.DATABASE_URL.replace("sqlite:///", ""))
    dump = "\n".join(con.iterdump())
    con.close()
    assert rid in dump and secret not in dump.replace("B307", "")


def test_retention_purges_old_reviews():
    rid = c.post("/reviews", json={"code": "x=1\n", "language": "python"}).json()["id"]
    with appdb.SessionLocal() as s:
        s.get(appdb.Review, rid).created_at = appdb.now() - timedelta(days=40)
        s.commit()
        assert appdb.purge_old(s, 0) == 0
        assert appdb.purge_old(s, 30) >= 1
    assert c.get(f"/reviews/{rid}").status_code == 404


def test_findings_endpoint_filters_and_search():
    rid = c.post("/reviews", json={"code": "import os\nx = eval(input())\n", "language": "python"}).json()["id"]
    sec = c.get(f"/reviews/{rid}/findings?category=Security").json()
    assert sec and all(f["category"] == "Security" for f in sec)
    assert all(f["source"] == "ai" for f in c.get(f"/reviews/{rid}/findings?source=ai").json())
    assert c.get("/reviews/nope/findings").status_code == 404
    assert any(r["id"] == rid for r in c.get("/reviews?severity=Medium&q=eval").json())
    assert c.get("/reviews?q=zzzznomatch").json() == []
    s = c.get("/stats").json()
    assert s["total_reviews"] >= 1 and "Security" in s["by_category"] and "Notice" not in s["by_category"]


def test_origin_check_and_rate_limit(monkeypatch):
    from app import ratelimit
    body = {"code": "x=1", "language": "python"}
    assert c.post("/reviews", json=body, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/reviews", json=body, headers={"Origin": "http://localhost:5173"}).status_code == 201
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    ratelimit.HITS.clear()
    assert (c.post("/reviews", json=body).status_code, c.post("/reviews", json=body).status_code) == (201, 429)
    ratelimit.HITS.clear()


def test_odd_legacy_rows_migrate_without_crashing_and_a_backup_is_written(tmp_path):
    path = tmp_path / "odd.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE reviews (id VARCHAR PRIMARY KEY, created_at DATETIME NOT NULL, language VARCHAR NOT NULL,"
                " provider VARCHAR NOT NULL, is_mock BOOLEAN NOT NULL, code_chars INTEGER NOT NULL,"
                " analyzers JSON NOT NULL, ai_error VARCHAR, findings JSON NOT NULL)")
    nulls = json.dumps([{"title": None, "severity": None, "id": None}, {"title": "ok"}])
    rows = [("empty", "[]"), ("nulls", nulls), ("garbage", "this is not json"), ("notalist", '{"a": 1}'),
            ("mixed", json.dumps(["str", 5, {"title": "T"}]))]
    for rid, raw in rows:
        con.execute("INSERT INTO reviews VALUES (?, '2026-01-01 00:00:00', 'python', 'mock', 1, 1, '{}', NULL, ?)",
                    (rid, raw))
    con.commit()
    con.close()
    before = path.read_bytes()
    appdb.init_db(f"sqlite:///{path}")
    con = sqlite3.connect(path)
    got = dict(con.execute("SELECT review_id, count(*) FROM findings GROUP BY review_id").fetchall())
    assert got == {"nulls": 2, "mixed": 1}
    assert con.execute("SELECT count(*) FROM reviews").fetchone()[0] == 5  # no review lost
    assert con.execute("SELECT severity, title FROM findings WHERE review_id='nulls' ORDER BY seq").fetchall() == \
        [("Informational", "(untitled)"), ("Informational", "ok")]
    con.close()
    backups = list(tmp_path.glob("odd.db.bak-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == before  # pre-migration copy is byte-identical
    appdb.init_db(f"sqlite:///{path}")  # up to date: no second backup
    assert len(list(tmp_path.glob("odd.db.bak-*"))) == 1


def test_fresh_database_needs_no_backup(tmp_path):
    appdb.init_db(f"sqlite:///{tmp_path / 'new.db'}")
    assert not list(tmp_path.glob("*.bak-*"))
