"""Gate A against a real, isolated PostgreSQL (opt-in).

Run only with a throwaway local instance:
  GATE_A_POSTGRES_TEST=1 GATE_A_POSTGRES_SERVICE=<svc> \
  STOCK_RESEARCH_TEST_DB_SERVICES=<svc> PGSERVICEFILE=<file> pytest tests/integration/...
The test drops and recreates schema ``ops`` in that database.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("GATE_A_POSTGRES_TEST") != "1" or not os.getenv("GATE_A_POSTGRES_SERVICE"),
    reason="isolated Gate A PostgreSQL not configured",
)

SERVICE = os.getenv("GATE_A_POSTGRES_SERVICE", "")
ROOT = Path(__file__).resolve().parents[2]
RUN = "strategy-eod-2026-07-24-local"
DAY = "2026-07-24"


def _legacy_schema_sql() -> str:
    """The snapshot schema exactly as on origin/main (pre Gate A)."""
    src = subprocess.run(
        ["git", "show", "origin/main:src/stock_research/review_evidence_snapshots.py"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    start = src.index('CREATE_REVIEW_EVIDENCE_SNAPSHOT_SQL = """') + len('CREATE_REVIEW_EVIDENCE_SNAPSHOT_SQL = """')
    return src[start:src.index('"""', start)]


def _exec(sql: str, params=None):
    from stock_research.db import connect
    with connect(SERVICE) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None


@pytest.fixture()
def legacy_db():
    _exec("DROP SCHEMA IF EXISTS ops CASCADE")
    _exec(_legacy_schema_sql())
    legacy = {"run_id": RUN, "trade_date": DAY, "asset_id": "CN:SH:600000",
              "digest_key": "k1", "source_type": "strategy_manifest", "source_name": "strategy_tech_bottleneck"}
    _exec("""INSERT INTO ops.review_item_snapshot (snapshot_id, run_id, trade_date, asset_id, digest_key,
             source_type, source_name, score_version, evidence_status, review_item_payload, payload_hash)
             VALUES ('legacy:1', %(run_id)s, %(trade_date)s, %(asset_id)s, %(digest_key)s, %(source_type)s,
                     %(source_name)s, 'strategy_topn', 'PARTIAL', '{}'::jsonb, 'h-legacy')""", legacy)
    yield
    _exec("DROP SCHEMA IF EXISTS ops CASCADE")


def _forward():
    _exec((ROOT / "deploy/migrations/gate_a_001_forward.sql").read_text())


def _item(score: float, digest_key: str = "k1") -> dict:
    return {"run_id": RUN, "trade_date": DAY, "asset_id": "CN:SH:600000", "digest_key": digest_key,
            "source_type": "strategy_manifest", "source_name": "strategy_tech_bottleneck",
            "score_version": "strategy_topn", "evidence_status": "PARTIAL", "score": score}


def test_forward_migration_keeps_legacy_rows_and_versions_new_writes(legacy_db):
    from stock_research import review_evidence_snapshots as res

    _forward()
    _forward()  # idempotent
    # legacy row survives untouched and is the current version, unverified
    (row,) = _exec("SELECT snapshot_id, publication_attempt_id FROM ops.review_item_snapshot_current")
    assert row["snapshot_id"] == "legacy:1" and row["publication_attempt_id"] is None

    pa = {"publication_attempt_id": "pubA", "snapshot_attempt_id": "snapA", "source_manifest_sha256": "shaA"}
    pb = {"publication_attempt_id": "pubB", "snapshot_attempt_id": "snapB", "source_manifest_sha256": "shaB"}
    a1 = res.build_review_item_snapshot(_item(1.0), provenance=pa)
    a2 = res.build_review_item_snapshot(_item(1.0, "k2"), provenance=pa)
    res.upsert_review_item_snapshot(a1, service=SERVICE)
    res.upsert_review_item_snapshot(a1, service=SERVICE)          # same content: no new row
    res.upsert_review_item_snapshot(a2, service=SERVICE)
    b1 = res.build_review_item_snapshot(_item(2.0), provenance=pb)  # publication B changes k1 only
    res.upsert_review_item_snapshot(b1, service=SERVICE)

    rows = _exec("SELECT snapshot_id, publication_attempt_id FROM ops.review_item_snapshot ORDER BY created_at")
    assert [r["publication_attempt_id"] for r in rows] == [None, "pubA", "pubA", "pubB"]  # history kept
    current = _exec("SELECT digest_key, publication_attempt_id FROM ops.review_item_snapshot_current ORDER BY digest_key")
    # current = latest publication batch only; k2 from A is NOT mixed into B
    assert [(r["digest_key"], r["publication_attempt_id"]) for r in current] == [("k1", "pubB")]

    listed = res.list_review_item_snapshots(run_id=RUN, service=SERVICE)
    assert [r["snapshot_id"] for r in listed] == [b1["snapshot_id"]]

    d = res.build_evidence_digest_snapshot({"run_id": RUN, "digest_key": "k1", "trade_date": DAY,
                                            "asset_id": "CN:SH:600000"}, provenance=pb)
    res.upsert_evidence_digest_snapshot(d, service=SERVICE)
    assert res.load_evidence_digest_snapshot(d["snapshot_id"], service=SERVICE)["source_manifest_sha256"] == "shaB"


def test_attempts_persist_backfill_and_abandon(legacy_db, tmp_path):
    from stock_research.db import connect
    from stock_research.run_attempts import DbAttemptStore, backfill_local_records, latest_published_attempt

    _forward()
    store = DbAttemptStore(service=SERVICE, fallback_dir=tmp_path)
    store.start({"attempt_id": "a1", "run_id": RUN, "trade_date": DAY, "module": "m", "trigger": "cron"})
    store.start({"attempt_id": "a2", "run_id": RUN, "trade_date": DAY, "module": "m", "trigger": "manual"})
    store.finish("a2", status="published", output_refs={"review_queue_manifest_sha256": "s"})
    rows = {r["attempt_id"]: r for r in _exec("SELECT attempt_id, status FROM ops.data_run_attempt")}
    assert rows == {"a1": {"attempt_id": "a1", "status": "abandoned"},
                    "a2": {"attempt_id": "a2", "status": "published"}}

    # DB-down attempt written locally, replayed twice -> one row, terminal state kept
    def down(_s):
        raise ConnectionError("down")
    offline = DbAttemptStore(service=SERVICE, fallback_dir=tmp_path / "offline", connect_fn=down)
    offline.start({"attempt_id": "a3", "run_id": RUN, "trade_date": DAY, "module": "m", "trigger": "cron"})
    offline.finish("a3", status="failed", failure_class="environment")
    with connect(SERVICE) as conn:
        assert backfill_local_records(conn, tmp_path / "offline") == {"records": 1}
    with connect(SERVICE) as conn:
        backfill_local_records(conn, tmp_path / "offline")
        pub = latest_published_attempt(conn, run_id=RUN, module="m")
    (a3,) = _exec("SELECT status, failure_class, recorded_from FROM ops.data_run_attempt WHERE attempt_id='a3'")
    assert dict(a3) == {"status": "failed", "failure_class": "environment", "recorded_from": "local_backfill"}
    assert pub["attempt_id"] == "a2"
    # a terminal attempt cannot be moved again
    store.finish("a2", status="failed")
    assert _exec("SELECT status FROM ops.data_run_attempt WHERE attempt_id='a2'")[0]["status"] == "published"


def test_rollback_restores_legacy_contract_without_losing_versions(legacy_db):
    from stock_research import review_evidence_snapshots as res

    _forward()
    for score in (1.0, 2.0, 3.0):
        res.upsert_review_item_snapshot(res.build_review_item_snapshot(_item(score)), service=SERVICE)
    before = _exec("SELECT count(*) n FROM ops.review_item_snapshot")[0]["n"]
    _exec((ROOT / "deploy/migrations/gate_a_001_rollback.sql").read_text())
    kept = _exec("SELECT count(*) n FROM ops.review_item_snapshot")[0]["n"]
    archived = _exec("SELECT count(*) n FROM ops.review_item_snapshot_version_archive")[0]["n"]
    assert kept == 1 and kept + archived == before
    with pytest.raises(Exception):
        _exec("""INSERT INTO ops.review_item_snapshot (snapshot_id, run_id, trade_date, asset_id, digest_key,
                 source_type, source_name, score_version, evidence_status, review_item_payload, payload_hash)
                 VALUES ('dup', %s, %s, 'x', 'k1', 't', 'n', 'v', 'e', '{}'::jsonb, 'h')""", [RUN, DAY])
