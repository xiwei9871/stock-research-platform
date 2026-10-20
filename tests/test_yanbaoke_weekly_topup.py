import pandas as pd
import pytest

from stock_research.yanbaoke_weekly_topup import (
    build_stock_priority_queue,
    choose_weekly_queue,
    dedupe_weekly_candidates,
    yanbaoke_report_id,
)


def test_report_id_uses_uuid_only_path_independent():
    row1 = {"uuid": "abc123", "title": "深度报告",
            "ts_code": "000001.SZ", "publish_date": "2026-10-15", "broker": "中信证券"}
    row2 = {**row1, "pdf_path": "/different/machine/path.pdf"}
    # same report, different local path -> SAME canonical id (fixes path-hash dup)
    assert yanbaoke_report_id(row1) == yanbaoke_report_id(row2) == "yanbaoke_abc123"


def test_report_id_fallback_without_uuid_is_path_independent():
    row = {"uuid": "", "title": "深度报告",
           "ts_code": "000001.SZ", "publish_date": "2026-10-15", "broker": "中信证券"}
    rid = yanbaoke_report_id(row)
    assert rid.startswith("yanbaoke_") and "pdf" not in rid


def test_priority_queue_buckets_by_evidence_gap():
    coverage = pd.DataFrame({
        "ts_code": ["000001.SZ", "600000.SH", "300001.SZ", "000002.SZ"],
        "report_count": [0, 12, 30, 5],
        "last_report_date": [None, "2026-10-01", "2025-06-01", "2026-09-20"],
        "parsed_count": [0, 10, 20, 4],
    })
    q = build_stock_priority_queue(coverage, stale_days=120, asof="2026-10-20")
    by_code = q.set_index("ts_code")
    assert by_code.loc["000001.SZ", "priority_bucket"] == "no_coverage"
    assert by_code.loc["300001.SZ", "priority_bucket"] == "stale_coverage"
    assert by_code.loc["600000.SH", "priority_bucket"] == "current"
    # ordering: no_coverage first, then stale, then thin/current
    assert list(q["ts_code"].head(2)) == ["000001.SZ", "300001.SZ"]


def test_dedupe_uuid_and_composite_keys():
    candidates = pd.DataFrame({
        "uuid": ["u1", "u2", "u3"],
        "ts_code": ["000001.SZ", "600000.SH", "300001.SZ"],
        "broker": ["中信", "华泰", "中金"],
        "publish_date": ["2026-10-15", "2026-10-14", "2026-10-13"],
        "title": ["报告A", "报告B", "报告C"],
    })
    kept, dropped = dedupe_weekly_candidates(
        candidates,
        existing_uuids={"u1"},
        existing_keys={("600000.SH", "华泰", "2026-10-14",
                        "报告b")},  # normalized
    )
    assert list(kept["uuid"]) == ["u3"]
    reasons = dict(zip(dropped["uuid"], dropped["drop_reason"]))
    assert reasons["u1"] == "uuid_exists"
    assert reasons["u2"] == "composite_exists"


def test_weekly_queue_respects_limit_caps_and_priority():
    rows = []
    for i in range(60):
        rows.append({"uuid": f"u{i}", "ts_code": f"{i:06d}.SZ",
                     "broker": "同一家券商" if i < 30 else f"券商{i}",
                     "publish_date": "2026-10-15", "title": f"T{i}",
                     "priority_score": 100 - i})
    candidates = pd.DataFrame(rows)
    chosen = choose_weekly_queue(
        candidates, weekly_limit=25, per_stock_cap=2, per_broker_cap=8)
    assert len(chosen) == 25
    # broker cap: max 8 from same broker even though top scores share it
    assert (chosen["broker"] == "同一家券商").sum() == 8
    # highest priority candidates survive
    assert "u0" in set(chosen["uuid"])


def test_weekly_queue_underfills_when_candidates_thin():
    candidates = pd.DataFrame({
        "uuid": ["u1"], "ts_code": ["000001.SZ"], "broker": ["中信"],
        "publish_date": ["2026-10-15"], "title": ["T"], "priority_score": [90.0]})
    chosen = choose_weekly_queue(candidates, weekly_limit=25)
    assert len(chosen) == 1  # never pads with low-quality filler


def test_run_weekly_topup_dry_run_emits_plan_without_api(tmp_path, monkeypatch):
    from stock_research import yanbaoke_weekly_topup as w

    fake_conn = object()
    monkeypatch.setattr(
        w, "build_weekly_plan",
        lambda conn, **kw: {
            "priority_queue": pd.DataFrame({
                "ts_code": ["000001.SZ"], "stock_name": ["平安"],
                "report_count": [0], "last_report_date": [None],
                "days_since_last_report": [None],
                "priority_bucket": ["no_coverage"],
            }),
            "bucket_counts": {"no_coverage": 1},
            "existing_uuids": {"old-uuid"},
            "existing_keys": set(),
        },
    )
    result = w.run_yanbaoke_weekly_topup(
        conn=fake_conn, dry_run=True, week_key="2026-W43",
        output_dir=tmp_path,
    )
    assert result["dry_run"] is True
    assert result["search_universe"] == 1
    assert result["bucket_counts"] == {"no_coverage": 1}


def test_run_weekly_topup_end_to_end_with_fakes(tmp_path, monkeypatch):
    from stock_research import yanbaoke_weekly_topup as w

    monkeypatch.setattr(
        w, "build_weekly_plan",
        lambda conn, **kw: {
            "priority_queue": pd.DataFrame({
                "ts_code": ["000001.SZ", "600000.SH"],
                "stock_name": ["平安", "浦发"],
                "priority_bucket": ["no_coverage", "stale_coverage"],
            }),
            "bucket_counts": {},
            "existing_uuids": {"old-uuid"},
            "existing_keys": set(),
        },
    )

    def fake_search(**kw):
        if kw["keyword"] == "平安":
            return {"reports": pd.DataFrame([
                {"uuid": "new-1", "title": "深度", "broker": "中信",
                 "publish_date": "2026-10-15"},
                {"uuid": "old-uuid", "title": "已存在", "broker": "中信",
                 "publish_date": "2026-10-15"},
            ])}
        return {"reports": pd.DataFrame()}

    monkeypatch.setattr(
        "stock_research.yanbaoke_reports.search_yanbaoke_reports",
        lambda **kw: fake_search(**kw),
    )
    monkeypatch.setattr(
        "stock_research.yanbaoke_reports.download_yanbaoke_report_pdf",
        lambda *, uuid, output_dir, **kw: {
            "uuid": uuid, "status": "downloaded",
            "pdf_path": str(tmp_path / f"{uuid}.pdf"),
            "filename": f"{uuid}.pdf",
        },
    )
    imported = {}
    monkeypatch.setattr(
        "stock_research.yanbaoke_reports.import_yanbaoke_report_downloads",
        lambda downloads, **kw: imported.update(downloads=downloads) or
        {"summary": {"source_rows": len(downloads)}},
    )

    result = w.run_yanbaoke_weekly_topup(
        conn=object(), dry_run=False, week_key="2026-W43",
        output_dir=tmp_path, ledger_path=tmp_path / "ledger.json",
        write_db=False,
    )
    ledger = result["ledger"]
    assert ledger["search_calls"] == 2
    assert ledger["dedup_dropped"] == 1       # old-uuid filtered
    assert ledger["planned_downloads"] == 1   # only new-1 left
    assert ledger["downloaded"] == 1
    assert ledger["api_charged"] == 1
    assert ledger["imported"] == 1
    assert len(imported["downloads"]) == 1
    on_disk = w.load_weekly_ledger(tmp_path / "ledger.json")
    assert on_disk["weeks"][0]["week_key"] == "2026-W43"
