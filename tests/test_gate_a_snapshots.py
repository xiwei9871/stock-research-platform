"""Gate A unit tests: post-publish snapshots, attempts, repair status, versions.

No database: snapshot runner, manifest writer and attempt store are fakes.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research import review_evidence_snapshots as res
from stock_research.eod_auto_repair_actions import repair_review_evidence_snapshots
from stock_research.eod_auto_repair_models import RepairStatus
from stock_research.run_attempts import DbAttemptStore, MemoryAttemptStore

DAY = "2026-07-24"
RUN = f"strategy-eod-{DAY}-local"


def _published(root: Path, rows: int = 15, variant: str = "A") -> Path:
    path = root / DAY / res.REVIEW_QUEUE_MANIFEST_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"asset_id": [f"CN:SH:{i:06d}" for i in range(rows)], "variant": variant}).to_csv(path, index=False)
    return path


def _call(root, store, *, runner, writer, expected=None, trigger="cron", pub="pub-1"):
    return res.run_post_publish_snapshots(
        run_id=RUN, trade_date=DAY, strategy_output_root=root, publication_attempt_id=pub,
        trigger=trigger, attempt_store=store, expected_manifest_sha256=expected,
        snapshot_runner=runner, manifest_writer=writer, service="test",
    )


def _runner(count, status="success", seen=None):
    def run(**kwargs):
        if seen is not None:
            seen.append(kwargs)
        return {"status": status, "review_item_snapshot_count": count,
                "evidence_digest_snapshot_count": count, "asset_count": count}
    return run


def test_snapshot_binds_publication_attempt_and_source_hash(tmp_path):
    src = _published(tmp_path)
    store, written, seen = MemoryAttemptStore(), [], []
    out = _call(tmp_path, store, runner=_runner(15, seen=seen), writer=written.append,
                expected=res.file_sha256(src))
    assert out["status"] == "success" and out["manifest_written"] is True
    prov = seen[0]["provenance"]
    assert prov["publication_attempt_id"] == "pub-1"
    assert prov["snapshot_attempt_id"] == out["attempt_id"]
    assert prov["source_manifest_sha256"] == res.file_sha256(src)
    assert seen[0]["strategy_output_root"] == tmp_path        # pinned, not "latest"
    assert seen[0]["service"] == "test"
    (entry,) = written
    assert entry["module"] == "review_evidence_snapshots" and entry["status"] == "success"
    assert entry["metadata"]["review_item_snapshot_count"] == 15
    assert entry["metadata"]["publication_attempt_id"] == "pub-1"
    rec = store.records[out["attempt_id"]]
    assert rec["status"] == "succeeded" and rec["parent_attempt_id"] == "pub-1"


def test_snapshot_refuses_a_different_published_version(tmp_path):
    _published(tmp_path, variant="B")
    store, written, seen = MemoryAttemptStore(), [], []
    out = _call(tmp_path, store, runner=_runner(15, seen=seen), writer=written.append,
                expected="sha-of-version-A")
    assert out["status"] == "failed" and "source_manifest_mismatch" in out["errors"]
    assert seen == []                                          # nothing snapshotted
    assert written[0]["status"] == "failed"
    assert store.records[out["attempt_id"]]["failure_class"] == "publish"


def test_snapshot_fails_when_source_missing(tmp_path):
    store, written = MemoryAttemptStore(), []
    out = _call(tmp_path, store, runner=_runner(15), writer=written.append)
    assert out["status"] == "failed" and "source_manifest_missing" in out["errors"]
    assert written[0]["status"] == "failed"


def test_snapshot_reconciles_written_count_with_source(tmp_path):
    _published(tmp_path, rows=15)
    store, written = MemoryAttemptStore(), []
    out = _call(tmp_path, store, runner=_runner(9), writer=written.append)
    assert out["status"] == "partial"
    assert written[0]["status"] == "partial"
    assert written[0]["row_count"] == 18                       # 9 items + 9 digests, real counts
    assert any("reconciliation" in w for w in written[0]["warnings"])


def test_snapshot_detects_source_replaced_during_run(tmp_path):
    src = _published(tmp_path)

    def runner(**kwargs):
        _published(tmp_path, variant="B")                      # another publication lands
        return {"status": "success", "review_item_snapshot_count": 15}

    out = _call(tmp_path, MemoryAttemptStore(), runner=runner, writer=lambda e: None,
                expected=res.file_sha256(src))
    assert out["status"] == "failed"
    assert "source_manifest_changed_during_snapshot" in out["errors"]


def test_manifest_writeback_failure_is_reported(tmp_path):
    _published(tmp_path)

    def broken(_entry):
        raise RuntimeError("db unavailable")

    out = _call(tmp_path, MemoryAttemptStore(), runner=_runner(15), writer=broken)
    assert out["status"] == "success" and out["manifest_written"] is False


def test_default_manifest_writer_uses_caller_service(tmp_path, monkeypatch):
    _published(tmp_path)
    calls = []
    import stock_research.data_run_manifest as drm
    monkeypatch.setattr(drm, "upsert_data_run_manifest",
                        lambda entry, service="DEFAULT": calls.append(service))
    res.run_post_publish_snapshots(
        run_id=RUN, trade_date=DAY, strategy_output_root=tmp_path, publication_attempt_id="p",
        trigger="cron", attempt_store=MemoryAttemptStore(), snapshot_runner=_runner(15),
        service="isolated_service",
    )
    assert calls == ["isolated_service"]


def test_repair_and_publication_attempts_are_separate(tmp_path):
    _published(tmp_path)
    store = MemoryAttemptStore()
    store.start({"attempt_id": "pub-1", "run_id": RUN, "module": "strategy_daily_eod_publication",
                 "trigger": "cron"})
    store.finish("pub-1", status="published")
    out = _call(tmp_path, store, runner=_runner(15), writer=lambda e: None, trigger="repair")
    rec = store.records[out["attempt_id"]]
    assert rec["trigger"] == "repair" and rec["module"] == "review_evidence_snapshots"
    assert rec["parent_attempt_id"] == "pub-1"
    assert store.records["pub-1"]["status"] == "published"


@pytest.mark.parametrize("result, expected", [
    ({"status": "success", "manifest_written": True}, RepairStatus.SUCCESS),
    ({"status": "success", "manifest_written": False}, RepairStatus.DEGRADED),
    ({"status": "partial"}, RepairStatus.DEGRADED),
    ({"status": "skipped"}, RepairStatus.SKIPPED),
    ({"status": "failed", "errors": ["source_manifest_missing"]}, RepairStatus.FAILED),
])
def test_repair_status_follows_real_result(result, expected):
    action = repair_review_evidence_snapshots(DAY, runner=lambda **_k: result)
    assert action.status == expected


def test_snapshot_ids_are_versioned_by_content():
    item = {"run_id": RUN, "digest_key": "k1", "trade_date": DAY, "asset_id": "CN:SH:600000"}
    a = res.build_review_item_snapshot(item, provenance={"publication_attempt_id": "p1"})
    b = res.build_review_item_snapshot({**item, "score": 1.0})
    assert a["snapshot_id"] != b["snapshot_id"]
    assert a["snapshot_id"] == res.build_review_item_snapshot(item)["snapshot_id"]
    assert a["publication_attempt_id"] == "p1" and b["publication_attempt_id"] is None
    d1 = res.build_evidence_digest_snapshot({"run_id": RUN, "digest_key": "k1", "trade_date": DAY})
    d2 = res.build_evidence_digest_snapshot({"run_id": RUN, "digest_key": "k1", "trade_date": DAY,
                                             "overall_status": "PARTIAL"})
    assert d1["snapshot_id"] != d2["snapshot_id"]


def test_snapshot_writes_never_update_existing_versions():
    import inspect

    for fn in (res.upsert_review_item_snapshot, res.upsert_evidence_digest_snapshot):
        src = inspect.getsource(fn)
        assert "ON CONFLICT (run_id, digest_key, payload_hash) DO NOTHING" in src
        assert "DO UPDATE" not in src


def test_official_requires_version_proof():
    ok_eod = {"status": "success"}
    pub = {"attempt_id": "p1", "status": "published"}
    snap = {"publication_attempt_id": "p1", "source_manifest_sha256": "h"}
    assert res.snapshot_official_status(snap, eod_status=ok_eod, publication_attempt=pub,
                                        published_manifest_sha256="h")["publication"] == "official"
    legacy = {"publication_attempt_id": None, "source_manifest_sha256": None}
    out = res.snapshot_official_status(legacy, eod_status=ok_eod, publication_attempt=None,
                                       published_manifest_sha256=None)
    assert out == {"publication": "derived_after_publish", "verification": "unverified",
                   "reasons": ["no_publication_attempt_id", "no_source_manifest_sha256"]}
    wrong = res.snapshot_official_status(snap, eod_status=ok_eod, publication_attempt=pub,
                                         published_manifest_sha256="other")
    assert wrong["verification"] == "unverified"
    assert res.snapshot_official_status(snap, eod_status={"status": "failed"}, publication_attempt=pub,
                                        published_manifest_sha256="h")["publication"] == "not_published"


def test_db_attempt_store_falls_back_to_local_record(tmp_path):
    def down(_service):
        raise ConnectionError("db unavailable")

    store = DbAttemptStore(service="test", fallback_dir=tmp_path, connect_fn=down)
    store.start({"attempt_id": "a1", "run_id": RUN, "module": "m", "trigger": "cron"})
    rec = store.finish("a1", status="failed", failure_class="environment")
    assert rec["persisted"] == "local"
    saved = json.loads((tmp_path / "run_record_a1.json").read_text())
    assert saved["status"] == "failed" and saved["failure_class"] == "environment"
    assert not list(tmp_path.glob("*.tmp"))


def test_memory_store_marks_stale_running_attempt_abandoned():
    store = MemoryAttemptStore()
    store.start({"attempt_id": "a1", "run_id": RUN, "module": "m", "trigger": "cron"})
    store.start({"attempt_id": "a2", "run_id": RUN, "module": "m", "trigger": "manual"})
    assert store.records["a1"]["status"] == "abandoned"
    assert store.records["a2"]["status"] == "running"


def test_attempt_rejects_unknown_values():
    store = MemoryAttemptStore()
    with pytest.raises(ValueError):
        store.start({"attempt_id": "x", "run_id": RUN, "module": "m", "trigger": "nightly"})
