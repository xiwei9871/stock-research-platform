import errno
import importlib.util
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from stock_research import strategy_daily_eod as eod
from stock_research import strategy_daily_eod_store as store
from stock_research import strategy_eod_publish as mature_publish

REAL_COMMIT_STRATEGY_PUBLICATION = eod.commit_strategy_publication


@pytest.fixture(autouse=True)
def _compat_publication_transaction(monkeypatch):
    def commit(*, manifest_entries, status_payload, service):
        for entry in manifest_entries:
            eod.upsert_data_run_manifest(entry, service=service)
        eod.upsert_strategy_daily_eod_status(status_payload, service=service)

    monkeypatch.setattr(eod, "commit_strategy_publication", commit)


def _write_complete_mature_release(
    *,
    output_root: Path,
    trade_date: str,
    manifest_upsert,
    counts: dict[str, int] | None = None,
) -> dict:
    counts = counts or {
        "lhb_shortline": 5,
        "mid_trend": 5,
        "tech_bottleneck": 5,
    }
    release = output_root / "research" / "strategy_daily_eod" / trade_date
    release.mkdir(parents=True)
    manifest_frames = []
    modules = {
        "lhb_shortline": "strategy_lhb_shortline",
        "mid_trend": "strategy_mid_trend",
        "tech_bottleneck": "strategy_tech_bottleneck",
    }
    for strategy_id, module in modules.items():
        rows = [
            {
                "trade_date": trade_date,
                "strategy_id": strategy_id,
                "asset_id": f"{strategy_id}-{rank}",
                "rank": rank,
                "review_tier": "top5_focus",
                "artifact_path": str(release / f"{module}_review.csv"),
            }
            for rank in range(1, counts[strategy_id] + 1)
        ]
        frame = pd.DataFrame(rows)
        review_path = release / f"{module}_review.csv"
        frame.to_csv(review_path, index=False)
        metadata = {"review_path": str(review_path)}
        if strategy_id == "mid_trend":
            for kind in ("equity", "positions", "trades"):
                path = release / f"{module}_{kind}.csv"
                path.write_text("value\n1\n", encoding="utf-8")
                metadata[f"{kind}_path"] = str(path)
        manifest_upsert(
            {
                "module": module,
                "status": "success",
                "trade_date": trade_date,
                "latest_trade_date": trade_date,
                "artifact_path": str(review_path),
                "metadata": metadata,
            }
        )
        manifest_frames.append(frame)
    manifest = pd.concat(manifest_frames, ignore_index=True)
    manifest_path = release / "review_queue_strategy_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    manifest_upsert(
        {
            "module": "review_queue_strategy_manifest",
            "status": "success",
            "trade_date": trade_date,
            "latest_trade_date": trade_date,
            "artifact_path": str(manifest_path),
            "metadata": {"review_path": str(manifest_path)},
        }
    )
    summary = {
        "run_id": f"strategy-eod-{trade_date}-local",
        "trade_date": trade_date,
        "output_dir": str(release),
        "manifest_modules": [*modules.values(), "review_queue_strategy_manifest"],
        "strategy_counts": counts,
        "review_rows": sum(counts.values()),
        "publishable": counts == {key: 5 for key in modules},
        "score_audit": {"status": "success", "strategy_counts": counts},
    }
    (release / "strategy_eod_publish_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    return summary


def test_official_runner_uses_mature_publisher_once_and_publishes_5x3(
    tmp_path: Path, monkeypatch
):
    calls = []
    persisted = []
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda entry, **_kwargs: persisted.append(entry))

    def publisher(**kwargs):
        calls.append(kwargs)
        return _write_complete_mature_release(**kwargs)

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert len(calls) == 1
    assert not summary["error_summary"], summary["error_summary"]
    assert summary["status"] == "success", summary
    assert summary["publishable"] is True
    assert summary["review_rows"] == 15
    assert summary["strategy_status"] == {
        "lhb_shortline": "success",
        "mid_trend": "success",
        "midtrend_artifacts": "success",
        "tech_bottleneck": "success",
    }
    assert persisted
    assert all(".versions" not in str(entry) for entry in persisted)
    assert all(
        str(entry.get("artifact_path") or "").startswith(str(tmp_path / "2026-07-24"))
        for entry in persisted
        if entry.get("artifact_path")
    )
    for entry in persisted:
        for key, value in (entry.get("metadata") or {}).items():
            if key.endswith("_path") and value:
                assert str(value).startswith(str(tmp_path / "2026-07-24"))


def test_official_runner_integrates_real_mature_publisher_manifest_shape(
    tmp_path: Path, monkeypatch
):
    release_root = tmp_path / "release"
    output_root = release_root / "outputs" / "research" / "strategy_daily_eod"
    report_path = release_root / "outputs" / "reports" / "daily.html"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("report", encoding="utf-8")
    provenance_path = tmp_path / "external-inputs" / "mid_trend_research_overlay.csv"
    provenance_path.parent.mkdir(parents=True)
    provenance_path.write_text("input", encoding="utf-8")
    persisted = []
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda entry, **_kwargs: persisted.append(entry))
    monkeypatch.setattr(mature_publish, "_ensure_strategy_dependencies", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mature_publish,
        "_build_base_manifest_entries",
        lambda **_kwargs: [{"module": "daily_bars", "status": "success", "metadata": {}}],
    )

    def write_strategy(*, run_id, trade_date, strategy_id, output_dir, started_at, **_kwargs):
        module = mature_publish.STRATEGY_EOD_MODULES[strategy_id]
        offset = 1 if strategy_id == "lhb_shortline" else 101
        rows = pd.DataFrame(
            [
                {
                    "trade_date": trade_date,
                    "strategy_id": strategy_id,
                    "asset_id": f"CN:SH:{offset + rank - 1:06d}",
                    "rank": rank,
                    "review_tier": "top5_focus",
                }
                for rank in range(1, 6)
            ]
        )
        review_path = output_dir / f"{module}_review.csv"
        rows.to_csv(review_path, index=False)
        metadata = {"review_path": str(review_path)}
        if strategy_id == "mid_trend":
            metadata["summary"] = {
                "data_coverage": {"research_overlay_path": str(provenance_path)}
            }
        for kind in ("equity", "positions", "trades"):
            path = output_dir / f"{module}_{kind}.csv"
            path.write_text("value\n1\n", encoding="utf-8")
            metadata[f"{kind}_path"] = str(path)
        entry = mature_publish.build_manifest_entry(
            run_id=run_id,
            run_date=trade_date,
            trade_date=trade_date,
            module=module,
            source="strategy_daily_eod",
            tier="tier1",
            status="success",
            started_at=started_at,
            latest_trade_date=trade_date,
            artifact_path=review_path,
            metadata=metadata,
        )
        return entry, rows

    monkeypatch.setattr(mature_publish, "_write_strategy_artifacts", write_strategy)
    monkeypatch.setattr(
        mature_publish,
        "_prepare_tech_bottleneck_base_candidate_source",
        lambda **kwargs: Path(kwargs["output_dir"]) / "tech-base.csv",
    )

    def write_tech(*, end_date, output_dir, manifest_upsert, **_kwargs):
        rows = pd.DataFrame(
            [
                {
                    "trade_date": end_date,
                    "strategy_id": "tech_bottleneck",
                    "asset_id": f"CN:SH:{200 + rank:06d}",
                    "rank": rank,
                    "review_tier": "top5_focus",
                }
                for rank in range(1, 6)
            ]
        )
        review_path = Path(output_dir) / "strategy_tech_bottleneck_review.csv"
        rows.to_csv(review_path, index=False)
        manifest_upsert(
            mature_publish.build_manifest_entry(
                run_id=f"strategy-eod-{end_date}-local",
                run_date=end_date,
                trade_date=end_date,
                module="strategy_tech_bottleneck",
                source="strategy_daily_eod",
                tier="tier1",
                status="success",
                latest_trade_date=end_date,
                artifact_path=review_path,
                metadata={"review_path": str(review_path)},
            )
        )
        return {"review_path": str(review_path)}

    monkeypatch.setattr(mature_publish, "run_tech_bottleneck_eod", write_tech)
    monkeypatch.setattr(
        mature_publish,
        "_write_strategy_score_audit_artifacts",
        lambda **_kwargs: {"status": "success"},
    )
    monkeypatch.setattr(mature_publish, "_write_eod_news_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(
        mature_publish,
        "_load_research_report_manifest_stats",
        lambda _trade_date: {"row_count": 1, "asset_count": 1, "latest_trade_date": "2026-07-24"},
    )
    monkeypatch.setattr(mature_publish, "_generated_report_files", lambda _trade_date: [str(report_path)])
    monkeypatch.setattr(mature_publish, "DEFAULT_REPORTS_DIR", report_path.parent)
    monkeypatch.setattr(
        mature_publish,
        "_write_review_evidence_snapshot_entry",
        lambda **_kwargs: {"module": "review_evidence_snapshots", "status": "partial"},
    )

    def publisher(**kwargs):
        return mature_publish.publish_strategy_eod(
            trade_date=kwargs["trade_date"],
            output_root=kwargs["output_root"],
            runner=lambda payload: {"strategy_id": payload["strategy_id"]},
            manifest_upsert=kwargs["manifest_upsert"],
        )

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=output_root,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert not summary["error_summary"], summary["error_summary"]
    assert summary["status"] == "success", summary
    assert summary["review_rows"] == 15
    generated = next(entry for entry in persisted if entry["module"] == "generated_reports")
    assert generated["artifact_path"] == str(report_path)
    assert generated["metadata"]["reports_dir"] == str(report_path.parent)
    mid = next(entry for entry in persisted if entry["module"] == "strategy_mid_trend")
    assert mid["metadata"]["summary"]["data_coverage"]["research_overlay_path"] == str(
        provenance_path
    )


def test_official_runner_rejects_external_metadata_review_path(tmp_path: Path, monkeypatch):
    external_review = tmp_path.parent / f"{tmp_path.name}-external-review.csv"
    external_review.write_text("review", encoding="utf-8")
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)

    def publisher(**kwargs):
        collected = []
        summary = _write_complete_mature_release(
            output_root=kwargs["output_root"],
            trade_date=kwargs["trade_date"],
            manifest_upsert=collected.append,
        )
        collected[0]["metadata"]["review_path"] = str(external_review)
        for entry in collected:
            kwargs["manifest_upsert"](entry)
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["status"] == "failed"
    assert "escapes controlled publication roots" in summary["error_summary"]


def test_official_runner_requires_real_midtrend_artifacts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")

    def publisher(**kwargs):
        summary = _write_complete_mature_release(**kwargs)
        release = (
            Path(kwargs["output_root"])
            / "research"
            / "strategy_daily_eod"
            / kwargs["trade_date"]
        )
        (release / "strategy_mid_trend_positions.csv").unlink()
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["publishable"] is False
    assert summary["strategy_status"]["midtrend_artifacts"] == "failed"
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"


def test_official_runner_rejects_manifest_paths_outside_staged_release(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")

    def publisher(**kwargs):
        collected = []
        summary = _write_complete_mature_release(
            output_root=kwargs["output_root"],
            trade_date=kwargs["trade_date"],
            manifest_upsert=collected.append,
        )
        escape_path = tmp_path.parent / f"{tmp_path.name}-escape.csv"
        escape_path.write_text("escape", encoding="utf-8")
        collected[0]["artifact_path"] = str(escape_path)
        for entry in collected:
            kwargs["manifest_upsert"](entry)
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["status"] == "failed"
    assert "escapes controlled publication roots" in summary["error_summary"]
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"


def test_official_runner_preserves_controlled_release_sibling_manifest_paths(
    tmp_path: Path, monkeypatch
):
    release_root = tmp_path / "release"
    output_root = release_root / "outputs" / "research" / "strategy_daily_eod"
    report_path = release_root / "outputs" / "reports" / "daily.html"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("report", encoding="utf-8")
    persisted = []
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda entry, **_kwargs: persisted.append(entry))

    def publisher(**kwargs):
        summary = _write_complete_mature_release(**kwargs)
        kwargs["manifest_upsert"](
            {
                "module": "generated_reports",
                "status": "success",
                "trade_date": kwargs["trade_date"],
                "latest_trade_date": kwargs["trade_date"],
                "artifact_path": str(report_path),
                "metadata": {
                    "report_paths": [str(report_path)],
                    "reports_dir": str(report_path.parent),
                },
            }
        )
        summary["manifest_modules"].append("generated_reports")
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=output_root,
        release_root=release_root,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["status"] == "success"
    reports = next(entry for entry in persisted if entry["module"] == "generated_reports")
    assert reports["artifact_path"] == str(report_path)
    assert reports["metadata"]["report_paths"] == [str(report_path)]
    assert reports["metadata"]["reports_dir"] == str(report_path.parent)
    assert "generated_reports" in summary["manifest_modules"]


def test_official_runner_allows_missing_descriptive_reports_dir(
    tmp_path: Path, monkeypatch
):
    release_root = tmp_path / "release"
    output_root = release_root / "outputs" / "research" / "strategy_daily_eod"
    report_path = release_root / "outputs" / "reports" / "daily.html"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("report", encoding="utf-8")
    missing_reports_dir = release_root / "outputs" / "reports-next"
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)

    def publisher(**kwargs):
        summary = _write_complete_mature_release(**kwargs)
        kwargs["manifest_upsert"](
            {
                "module": "generated_reports",
                "status": "partial",
                "trade_date": kwargs["trade_date"],
                "latest_trade_date": kwargs["trade_date"],
                "artifact_path": str(report_path),
                "metadata": {
                    "report_files": [str(report_path)],
                    "reports_dir": str(missing_reports_dir),
                },
            }
        )
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=output_root,
        release_root=release_root,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["status"] == "success"
    assert not missing_reports_dir.exists()


def test_official_runner_requires_concrete_report_files_to_exist(
    tmp_path: Path, monkeypatch
):
    release_root = tmp_path / "release"
    output_root = release_root / "outputs" / "research" / "strategy_daily_eod"
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)

    def publisher(**kwargs):
        summary = _write_complete_mature_release(**kwargs)
        kwargs["manifest_upsert"](
            {
                "module": "generated_reports",
                "status": "partial",
                "trade_date": kwargs["trade_date"],
                "latest_trade_date": kwargs["trade_date"],
                "metadata": {
                    "report_files": [
                        str(release_root / "outputs" / "reports" / "missing.html")
                    ],
                },
            }
        )
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=output_root,
        release_root=release_root,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["status"] == "failed"
    assert "manifest path does not exist" in summary["error_summary"]


def test_official_runner_rejects_key_manifest_artifact_in_release_sibling(
    tmp_path: Path, monkeypatch
):
    release_root = tmp_path / "release"
    output_root = release_root / "outputs" / "research" / "strategy_daily_eod"
    wrong_path = release_root / "outputs" / "reports" / "wrong.csv"
    wrong_path.parent.mkdir(parents=True)
    wrong_path.write_text("wrong", encoding="utf-8")
    canonical = output_root / "2026-07-24"
    canonical.mkdir(parents=True)
    (canonical / "marker").write_text("old", encoding="utf-8")
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)

    def publisher(**kwargs):
        collected = []
        summary = _write_complete_mature_release(
            output_root=kwargs["output_root"],
            trade_date=kwargs["trade_date"],
            manifest_upsert=collected.append,
        )
        for entry in collected:
            if entry["module"] == "strategy_lhb_shortline":
                entry["artifact_path"] = str(wrong_path)
            kwargs["manifest_upsert"](entry)
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=output_root,
        release_root=release_root,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["publishable"] is False
    assert summary["strategy_status"]["lhb_shortline"] == "failed"
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"


@pytest.mark.parametrize(
    ("missing_module", "failed_strategy"),
    [
        ("strategy_lhb_shortline", "lhb_shortline"),
        ("strategy_tech_bottleneck", "tech_bottleneck"),
        ("review_queue_strategy_manifest", None),
    ],
)
def test_official_runner_requires_all_key_success_manifest_entries(
    tmp_path: Path, monkeypatch, missing_module: str, failed_strategy: str | None
):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")

    def publisher(**kwargs):
        collected = []
        summary = _write_complete_mature_release(
            output_root=kwargs["output_root"],
            trade_date=kwargs["trade_date"],
            manifest_upsert=collected.append,
        )
        for entry in collected:
            if entry["module"] != missing_module:
                kwargs["manifest_upsert"](entry)
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["publishable"] is False
    if failed_strategy:
        assert summary["strategy_status"][failed_strategy] == "failed"
    assert missing_module not in summary["manifest_modules"]
    assert "missing required success manifest" in summary["error_summary"]
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"


def test_official_runner_rejects_stale_key_manifest_date(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)

    def publisher(**kwargs):
        collected = []
        summary = _write_complete_mature_release(
            output_root=kwargs["output_root"],
            trade_date=kwargs["trade_date"],
            manifest_upsert=collected.append,
        )
        for entry in collected:
            if entry["module"] == "strategy_tech_bottleneck":
                entry["latest_trade_date"] = "2026-07-23"
            kwargs["manifest_upsert"](entry)
        return summary

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["publishable"] is False
    assert summary["strategy_status"]["tech_bottleneck"] == "failed"
    assert "strategy_tech_bottleneck on 2026-07-24" in summary["error_summary"]


@pytest.mark.parametrize("failure", ["nth_manifest", "status"])
def test_official_runner_rolls_back_canonical_when_publication_transaction_fails(
    tmp_path: Path, monkeypatch, failure: str
):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")
    transaction_calls = []

    def failing_transaction(*, manifest_entries, status_payload, service):
        transaction_calls.append((manifest_entries, status_payload, service))
        raise RuntimeError(f"{failure} write failed")

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **kwargs: _write_complete_mature_release(**kwargs),
        publication_transaction=failing_transaction,
        service="test",
    )

    assert len(transaction_calls) == 1
    assert summary["status"] == "failed"
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"
    assert Path(summary["summary_path"]).exists()
    assert str(summary["summary_path"]).startswith(str(tmp_path / ".failures"))


def test_official_runner_preserves_recovery_scene_when_rollback_fails(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")
    real_begin = eod.begin_atomic_publish

    def begin_with_failed_rollback(staging, target):
        handle = real_begin(staging, target)
        handle.rollback = lambda: (_ for _ in ()).throw(OSError("rollback unavailable"))
        return handle

    monkeypatch.setattr(eod, "begin_atomic_publish", begin_with_failed_rollback)

    with pytest.raises(
        RuntimeError,
        match="strategy publication rollback failed; manual recovery required",
    ):
        eod.run_strategy_daily_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            dependency_checker=lambda **_kwargs: {"status": "success"},
            publisher=lambda **kwargs: _write_complete_mature_release(**kwargs),
            publication_transaction=lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("DB failed")
            ),
            service="test",
        )

    assert not (canonical / "marker").exists()
    assert (canonical / "strategy_eod_publish_summary.json").exists()
    backups = list((tmp_path / ".versions" / "2026-07-24").glob("strategy-eod-*"))
    assert any((backup / "marker").exists() for backup in backups)
    audits = list((tmp_path / ".failures" / "2026-07-24").glob("*/strategy_eod_publish_summary.json"))
    assert audits
    assert "rollback_failure" in audits[-1].read_text(encoding="utf-8")


def test_official_runner_handles_pre_switch_relocation_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")
    real_relocate = eod._relocate_review_manifest_paths
    calls = 0

    def fail_second_relocation(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("relocation failed")
        return real_relocate(*args, **kwargs)

    monkeypatch.setattr(eod, "_relocate_review_manifest_paths", fail_second_relocation)

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **kwargs: _write_complete_mature_release(**kwargs),
        service="test",
    )

    assert summary["status"] == "failed"
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"
    assert Path(summary["summary_path"]).exists()
    assert not list((tmp_path / ".versions" / "2026-07-24").glob("strategy-eod-*"))


def test_official_runner_handles_staging_summary_write_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")
    real_write_text = Path.write_text
    summary_writes = 0

    def fail_official_summary_write(path, *args, **kwargs):
        nonlocal summary_writes
        if path.name == "strategy_eod_publish_summary.json":
            summary_writes += 1
            if summary_writes == 2:
                raise OSError("summary write failed")
        return real_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_official_summary_write)

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **kwargs: _write_complete_mature_release(**kwargs),
        service="test",
    )

    assert summary["status"] == "failed"
    assert "summary write failed" in summary["error_summary"]
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"
    assert Path(summary["summary_path"]).exists()


def test_official_runner_rejects_legacy_runner_injection(tmp_path: Path):
    with pytest.raises(ValueError, match="legacy strategy runner injection is unsupported"):
        eod.run_strategy_daily_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            lhb_runner=lambda **_kwargs: {},
        )


def test_official_runner_rejects_output_root_outside_explicit_release(tmp_path: Path):
    release_root = tmp_path / "release"
    outside = tmp_path / "outside" / "strategy_daily_eod"
    with pytest.raises(ValueError, match="contained within release root"):
        eod.run_strategy_daily_eod(
            trade_date="2026-07-24",
            output_root=outside,
            release_root=release_root,
        )


def test_official_runner_rejects_output_root_symlink_escape(tmp_path: Path):
    release_root = tmp_path / "release"
    release_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_output = release_root / "strategy_daily_eod"
    linked_output.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="contained within release root"):
        eod.run_strategy_daily_eod(
            trade_date="2026-07-24",
            output_root=linked_output,
            release_root=release_root,
        )


@pytest.mark.parametrize("error_number", [errno.ENOSYS, errno.EXDEV])
def test_official_runner_preserves_canonical_when_atomic_begin_fails(
    tmp_path: Path, monkeypatch, error_number: int
):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")
    monkeypatch.setattr(
        eod,
        "_atomic_exchange_directories",
        lambda *_args: (_ for _ in ()).throw(OSError(error_number, "atomic failed")),
    )

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **kwargs: _write_complete_mature_release(**kwargs),
        publication_transaction=lambda **_kwargs: pytest.fail("DB must not start"),
        service="test",
    )

    assert summary["status"] == "failed"
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"
    assert Path(summary["summary_path"]).exists()


def test_publication_transaction_uses_one_connection_and_rolls_back_on_status_failure(
    monkeypatch,
):
    connection = object()
    observed = {"entered": 0, "exit_error": None, "manifest_connections": []}

    class TransactionContext:
        def __enter__(self):
            observed["entered"] += 1
            return connection

        def __exit__(self, error_type, _error, _traceback):
            observed["exit_error"] = error_type
            return False

    monkeypatch.setattr(eod, "connect", lambda _service: TransactionContext())
    monkeypatch.setattr(
        eod,
        "upsert_data_run_manifest_with_connection",
        lambda _entry, *, conn: observed["manifest_connections"].append(conn),
    )
    monkeypatch.setattr(
        eod,
        "upsert_strategy_daily_eod_status_with_connection",
        lambda _payload, *, conn: (_ for _ in ()).throw(RuntimeError("status failed")),
    )

    with pytest.raises(RuntimeError, match="status failed"):
        REAL_COMMIT_STRATEGY_PUBLICATION(
            manifest_entries=[{"module": "one"}, {"module": "two"}],
            status_payload={"status": "success"},
            service="test",
        )

    assert observed["entered"] == 1
    assert observed["manifest_connections"] == [connection, connection]
    assert observed["exit_error"] is RuntimeError


def test_publication_transaction_rolls_back_on_nth_manifest_failure(monkeypatch):
    connection = object()
    observed = {"exit_error": None, "manifest_calls": 0, "status_calls": 0}

    class TransactionContext:
        def __enter__(self):
            return connection

        def __exit__(self, error_type, _error, _traceback):
            observed["exit_error"] = error_type
            return False

    def write_manifest(_entry, *, conn):
        assert conn is connection
        observed["manifest_calls"] += 1
        if observed["manifest_calls"] == 2:
            raise RuntimeError("second manifest failed")

    monkeypatch.setattr(eod, "connect", lambda _service: TransactionContext())
    monkeypatch.setattr(eod, "upsert_data_run_manifest_with_connection", write_manifest)
    monkeypatch.setattr(
        eod,
        "upsert_strategy_daily_eod_status_with_connection",
        lambda *_args, **_kwargs: observed.update(status_calls=observed["status_calls"] + 1),
    )

    with pytest.raises(RuntimeError, match="second manifest failed"):
        REAL_COMMIT_STRATEGY_PUBLICATION(
            manifest_entries=[{"module": "one"}, {"module": "two"}, {"module": "three"}],
            status_payload={"status": "success"},
            service="test",
        )

    assert observed["manifest_calls"] == 2
    assert observed["status_calls"] == 0
    assert observed["exit_error"] is RuntimeError


def test_official_runner_does_not_replace_canonical_for_invalid_counts(
    tmp_path: Path, monkeypatch
):
    persisted = []
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda entry, **_kwargs: persisted.append(entry))
    canonical = tmp_path / "2026-07-24"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **kwargs: _write_complete_mature_release(
            **kwargs,
            counts={"lhb_shortline": 5, "mid_trend": 5, "tech_bottleneck": 0},
        ),
        service="test",
    )

    assert summary["status"] == "partial"
    assert summary["publishable"] is False
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"
    assert str(summary["summary_path"]).startswith(str(tmp_path / ".failures"))
    assert not persisted


def test_official_runner_does_not_commit_success_manifest_when_publisher_raises(
    tmp_path: Path, monkeypatch
):
    persisted = []
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda entry, **_kwargs: persisted.append(entry))

    def publisher(**kwargs):
        kwargs["manifest_upsert"](
            {"module": "strategy_lhb_shortline", "status": "success"}
        )
        raise RuntimeError("engine exploded")

    summary = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=publisher,
        service="test",
    )

    assert summary["status"] == "failed"
    assert summary["publishable"] is False
    assert "engine exploded" in summary["error_summary"]
    assert not persisted


def test_atomic_publish_switches_existing_symlink_to_new_version(tmp_path: Path):
    versions = tmp_path / ".versions" / "2026-07-02"
    old_version = versions / "old"
    new_version = versions / "new"
    old_version.mkdir(parents=True)
    new_version.mkdir()
    (old_version / "marker").write_text("old", encoding="utf-8")
    (new_version / "marker").write_text("new", encoding="utf-8")
    canonical = tmp_path / "2026-07-02"
    canonical.symlink_to(os.path.relpath(old_version, canonical.parent), target_is_directory=True)

    eod._atomic_publish_directory(new_version, canonical)

    assert canonical.is_symlink()
    assert (canonical / "marker").read_text(encoding="utf-8") == "new"
    assert canonical.resolve() == new_version.resolve()


def test_atomic_publish_handle_rolls_back_existing_symlink(tmp_path: Path):
    versions = tmp_path / ".versions" / "2026-07-02"
    old_version = versions / "old"
    new_version = versions / "new"
    old_version.mkdir(parents=True)
    new_version.mkdir()
    (old_version / "marker").write_text("old", encoding="utf-8")
    (new_version / "marker").write_text("new", encoding="utf-8")
    canonical = tmp_path / "2026-07-02"
    canonical.symlink_to(os.path.relpath(old_version, canonical.parent), target_is_directory=True)

    handle = eod.begin_atomic_publish(new_version, canonical)
    assert (canonical / "marker").read_text(encoding="utf-8") == "new"
    handle.rollback()

    assert canonical.is_symlink()
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"


def test_atomic_publish_fails_closed_when_exchange_is_unavailable_for_real_directory(
    tmp_path: Path,
    monkeypatch,
):
    versions = tmp_path / ".versions" / "2026-07-02"
    staging = versions / "new"
    staging.mkdir(parents=True)
    (staging / "marker").write_text("new", encoding="utf-8")
    canonical = tmp_path / "2026-07-02"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")
    monkeypatch.setattr(
        eod,
        "_atomic_exchange_directories",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.ENOSYS, "unsupported")),
    )

    try:
        eod._atomic_publish_directory(staging, canonical)
    except RuntimeError as exc:
        assert "existing real directory preserved" in str(exc)
    else:
        raise AssertionError("real-directory migration must fail closed")

    assert not canonical.is_symlink()
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"
    assert (staging / "marker").read_text(encoding="utf-8") == "new"


def test_atomic_publish_rejects_cross_device_exchange_without_fallback(
    tmp_path: Path,
    monkeypatch,
):
    versions = tmp_path / ".versions" / "2026-07-02"
    staging = versions / "new"
    staging.mkdir(parents=True)
    canonical = tmp_path / "2026-07-02"
    canonical.mkdir()
    (canonical / "marker").write_text("old", encoding="utf-8")
    monkeypatch.setattr(
        eod,
        "_atomic_exchange_directories",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EXDEV, "cross-device")),
    )

    try:
        eod._atomic_publish_directory(staging, canonical)
    except OSError as exc:
        assert exc.errno == errno.EXDEV
    else:
        raise AssertionError("cross-device exchange must be rejected")

    assert not canonical.is_symlink()
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"


def test_symlink_publication_retains_at_most_three_total_versions(tmp_path: Path):
    versions = tmp_path / ".versions" / "2026-07-02"
    versions.mkdir(parents=True)
    canonical = tmp_path / "2026-07-02"
    for index in range(5):
        version = versions / f"version-{index}"
        version.mkdir()
        os.utime(version, ns=(index + 1, index + 1))
    canonical.symlink_to(
        os.path.relpath(versions / "version-3", canonical.parent),
        target_is_directory=True,
    )

    eod._atomic_publish_directory(versions / "version-4", canonical)

    retained = [path for path in versions.iterdir() if path.is_dir()]
    assert len(retained) <= 3
    assert canonical.resolve() == (versions / "version-4").resolve()


def test_status_payload_and_schema():
    payload = store.build_status_payload(
        trade_date="2026-06-24",
        status="failed",
        dependency_check_status="failed",
        lhb_shortline_status="skipped",
        mid_trend_status="skipped",
        midtrend_artifacts_status="skipped",
        tech_bottleneck_status="skipped",
        review_rows=0,
        output_dir="/tmp/out",
        summary_path="/tmp/out/summary.json",
        error_summary="deps missing",
    )

    assert payload["trade_date"] == "2026-06-24"
    assert payload["mid_trend_status"] == "skipped"
    assert payload["midtrend_artifacts_status"] == "skipped"
    assert "ops.strategy_daily_eod_status" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "'partial'" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "'blocked'" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "pg_get_constraintdef" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "IF constraint_definition IS NULL" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert store.STRATEGY_DAILY_EOD_STATUS_SQL.index(
        "IF constraint_definition IS NULL"
    ) < store.STRATEGY_DAILY_EOD_STATUS_SQL.index("DROP CONSTRAINT IF EXISTS")
    assert "ADD COLUMN midtrend_artifacts_status text" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "ADD COLUMN IF NOT EXISTS" not in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "FROM pg_attribute" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "attnotnull" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "IF NOT column_exists" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "ELSIF NOT column_not_null" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "SET midtrend_artifacts_status = 'skipped'" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "COALESCE(midtrend_artifacts_status, mid_trend_status" not in store.STRATEGY_DAILY_EOD_STATUS_SQL


def test_status_upsert_and_reader_include_midtrend_artifacts(monkeypatch):
    captured = {}
    monkeypatch.setattr(store, "execute", lambda conn, sql, payload: captured.update(sql=sql, payload=payload))
    payload = {
        "trade_date": "2026-07-24",
        "status": "success",
        "dependency_check_status": "success",
        "lhb_shortline_status": "success",
        "mid_trend_status": "success",
        "midtrend_artifacts_status": "success",
        "tech_bottleneck_status": "success",
        "review_rows": 15,
        "output_dir": "/tmp/out",
        "summary_path": "/tmp/out/summary.json",
        "error_summary": None,
    }
    store.upsert_strategy_daily_eod_status_with_connection(payload, conn=object())
    assert "midtrend_artifacts_status" in captured["sql"]
    assert captured["payload"]["midtrend_artifacts_status"] == "success"

    class Context:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(store, "connect", lambda _service: Context())
    monkeypatch.setattr(
        store,
        "fetch_all",
        lambda _conn, sql, _params: captured.update(select_sql=sql) or [payload],
    )
    loaded = store.load_strategy_daily_eod_status("2026-07-24", service="test")
    assert loaded["midtrend_artifacts_status"] == "success"
    assert "midtrend_artifacts_status" in captured["select_sql"]


def test_run_strategy_daily_eod_writes_summary_and_status(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda payload, **_kwargs: captured.update(payload=payload))
    monkeypatch.setattr(
        eod,
        "check_strategy_daily_eod_dependencies",
        lambda **_kwargs: {"status": "success"},
    )

    def runner(*, trade_date, output_dir, service):
        frame = pd.DataFrame(
            [
                {
                    "trade_date": trade_date,
                    "asset_id": "CN:SH:600000",
                    "rank": 1,
                    "score_total": 10,
                    "score_source": "stub",
                    "score_explanation": "stub",
                    "strategy_id": "stub",
                    "strategy_name": "stub",
                    "strategy_run_id": "stub",
                    "source_type": "stub",
                    "source_name": "stub",
                    "source_rank": 1,
                    "review_tier": "top5_focus",
                }
            ]
        )
        (Path(output_dir) / "strategy_lhb_shortline_review.csv").write_text(frame.to_csv(index=False), encoding="utf-8")
        return {"status": "success", "review_rows": 1, "paths": {"review": str(Path(output_dir) / "strategy_lhb_shortline_review.csv")}}

    output_dir = tmp_path / "2026-06-24"
    output_dir.mkdir(parents=True)
    official_manifest = output_dir / "review_queue_strategy_manifest.csv"
    official_manifest.write_text("official dashboard manifest\n", encoding="utf-8")
    official_lhb = output_dir / "strategy_lhb_shortline_review.csv"
    official_mid = output_dir / "strategy_mid_trend_review.csv"
    official_tech = output_dir / "strategy_tech_bottleneck_review.csv"
    official_lhb.write_text("official lhb\n", encoding="utf-8")
    official_mid.write_text("official mid\n", encoding="utf-8")
    official_tech.write_text("official tech\n", encoding="utf-8")

    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **kwargs: _write_complete_mature_release(
            **kwargs,
            counts={"lhb_shortline": 1, "mid_trend": 1, "tech_bottleneck": 1},
        ),
    )

    summary_path = tmp_path / "2026-06-24" / "strategy_eod_publish_summary.json"
    assert result["status"] == "partial"
    assert not summary_path.exists()
    assert official_manifest.read_text(encoding="utf-8") == "official dashboard manifest\n"
    assert official_lhb.read_text(encoding="utf-8") == "official lhb\n"
    assert official_mid.read_text(encoding="utf-8") == "official mid\n"
    assert official_tech.read_text(encoding="utf-8") == "official tech\n"
    failure_summary = Path(result["summary_path"])
    assert failure_summary.exists()
    assert failure_summary.parent.parent.parent == tmp_path / ".failures"
    assert Path(result["output_dir"]) == failure_summary.parent
    assert captured["payload"]["output_dir"] == str(failure_summary.parent)
    assert captured["payload"]["summary_path"] == str(failure_summary)
    assert result["midtrend_artifacts"] == {}
    assert result["manifest_modules"] == [
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "review_queue_strategy_manifest",
    ]
    assert captured["payload"]["status"] == "partial"


def test_failed_strategy_publication_retains_only_ten_audit_summaries(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)

    for _ in range(12):
        result = eod.run_strategy_daily_eod(
            trade_date="2026-06-24",
            output_root=tmp_path,
            dependency_checker=lambda **_kwargs: {"status": "failed", "reason": "missing"},
        )
        assert Path(result["summary_path"]).exists()

    failure_root = tmp_path / ".failures" / "2026-06-24"
    retained = [path for path in failure_root.iterdir() if path.is_dir()]
    assert len(retained) == 10


def test_official_strategy_runner_writes_task7_canonical_release(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)
    canonical_dir = tmp_path / "2026-07-02"
    canonical_dir.mkdir()
    (canonical_dir / "old_release.marker").write_text("old", encoding="utf-8")
    original_switch = eod.begin_atomic_publish
    switch_observations = []

    def observed_switch(staging, canonical):
        switch_observations.append((canonical / "old_release.marker").read_text(encoding="utf-8"))
        return original_switch(staging, canonical)

    monkeypatch.setattr(eod, "begin_atomic_publish", observed_switch)

    def runner_for(strategy_id, filename):
        def runner(*, trade_date, output_dir, service):
            rows = [
                {
                    "trade_date": trade_date,
                    "strategy_id": strategy_id,
                    "rank": rank,
                    "asset_id": f"{strategy_id}-{rank}",
                    "review_tier": "top5_focus",
                }
                for rank in range(1, 6)
            ]
            path = Path(output_dir) / filename
            pd.DataFrame(rows).to_csv(path, index=False)
            return {"status": "success", "review_rows": 5, "paths": {"review": str(path)}}

        return runner

    result = eod.run_strategy_daily_eod(
        trade_date="2026-07-02",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **kwargs: _write_complete_mature_release(**kwargs),
    )

    assert result["publishable"] is True
    assert switch_observations == ["old"]
    assert not (canonical_dir / "old_release.marker").exists()
    assert all(
        str(path).startswith(str(canonical_dir))
        for path in result["midtrend_artifacts"].values()
    )
    validator_path = Path(__file__).resolve().parents[1] / "deploy" / "validate_strategy_release.py"
    spec = importlib.util.spec_from_file_location("validate_strategy_release", validator_path)
    assert spec and spec.loader
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.validate_strategy_release(
        output_dir=tmp_path / "2026-07-02",
        trade_date="2026-07-02",
    )


def test_run_strategy_daily_eod_writes_midtrend_v1_v2_and_review_artifacts(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda payload, **_kwargs: captured.update(payload=payload))
    monkeypatch.setattr(eod, "upsert_data_run_manifest", lambda *_args, **_kwargs: None)

    def runner(*, trade_date, output_dir, service):
        path = Path(output_dir) / "strategy_mid_trend_review.csv"
        pd.DataFrame([{"trade_date": trade_date, "asset_id": "A"}]).to_csv(path, index=False)
        return {
            "status": "success",
            "review_rows": 1,
            "paths": {"review": str(path)},
        }

    def artifact_builder(*, trade_date, output_dir, service):
        files = {}
        for name in [
            "midtrend_v1_top5_reference.csv",
            "midtrend_v2_top10_candidate.csv",
            "midtrend_canonical_pit_review_labels.csv",
            "midtrend_post_exit_watch_daily_review_lite.json",
        ]:
            path = Path(output_dir) / name
            path.write_text("x", encoding="utf-8")
            files[name] = str(path)
        return {"status": "success", "paths": files, "review_rows": 0}

    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **kwargs: _write_complete_mature_release(**kwargs),
    )

    assert result["status"] == "success"
    assert result["strategy_status"]["midtrend_artifacts"] == "success"
    assert set(result["midtrend_artifacts"]) == {
        "review_path",
        "equity_path",
        "positions_path",
        "trades_path",
    }
    assert Path(result["summary_path"]).exists()
    assert captured["payload"]["status"] == "success"
    assert captured["payload"]["midtrend_artifacts_status"] == "success"


def test_run_strategy_daily_eod_flat_failed_dependency_blocks_all_strategies(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda payload, **_kwargs: captured.update(payload=payload))

    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "failed", "reason": "deps missing"},
    )

    assert result["status"] == "failed"
    assert set(result["strategy_status"].values()) == {"blocked"}
    assert all("deps missing" in reason for reason in result["strategy_errors"].values())
    assert captured["payload"]["dependency_check_status"] == "failed"


def test_run_strategy_daily_eod_intraday_failure_only_blocks_lhb(tmp_path: Path, monkeypatch):
    captured = {}
    calls = []
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda payload, **_kwargs: captured.update(payload=payload))

    def publisher(**_kwargs):
        calls.append("publisher")
        raise AssertionError("dependency failure must block atomic publisher")

    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {
            "common": {"status": "success"},
            "intraday": {
                "status": "failed",
                "reason": "baostock login failed: 10002007",
            },
        },
        publisher=publisher,
    )

    assert calls == []
    assert result["status"] == "failed"
    assert result["review_rows"] == 0
    assert result["strategy_status"] == {
        "lhb_shortline": "blocked",
        "mid_trend": "skipped",
        "midtrend_artifacts": "skipped",
        "tech_bottleneck": "skipped",
    }
    assert result["strategy_errors"]["lhb_shortline"] == "intraday: baostock login failed: 10002007"
    assert result["dependency_check"]["intraday"]["reason"] == "baostock login failed: 10002007"
    assert captured["payload"]["status"] == "failed"
    assert captured["payload"]["dependency_check_status"] == "failed"
    assert captured["payload"]["midtrend_artifacts_status"] == "skipped"


def test_run_strategy_daily_eod_common_failure_blocks_all_runners(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)

    def runner(name):
        def run(**_kwargs):
            calls.append(name)
            return {"status": "success", "review_rows": 1, "paths": {}}

        return run

    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {
            "common": {"status": "failed", "reason": "daily_status=failed"},
            "intraday": {"status": "success"},
        },
    )

    assert calls == []
    assert result["status"] == "failed"
    assert set(result["strategy_status"].values()) == {"blocked"}
    assert result["strategy_errors"]["tech_bottleneck"] == "common: daily_status=failed"


def test_run_strategy_daily_eod_records_independent_runner_failure_reason(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)

    def success(**_kwargs):
        return {"status": "success", "review_rows": 1, "paths": {}}

    def failed(**_kwargs):
        return {"status": "failed", "review_rows": 0, "paths": {}, "reason": "model unavailable"}

    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        publisher=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )

    assert result["status"] == "failed"
    assert result["strategy_status"]["mid_trend"] == "failed"
    assert "model unavailable" in result["strategy_errors"]["mid_trend"]


def test_check_strategy_daily_eod_dependencies_returns_common_and_intraday(monkeypatch):
    monkeypatch.setattr(
        eod,
        "_fetch_one",
        lambda *_args, **_kwargs: [
            {
                "daily_status": "success",
                "minute5_status": "failed",
                "deps_status": "success",
                "failed_jobs": [
                    {
                        "stage": "minute5",
                        "source": "baostock",
                        "error_summary": "login failed: 10002007",
                    }
                ],
            }
        ],
    )

    result = eod.check_strategy_daily_eod_dependencies(trade_date="2026-06-24")

    assert result["common"] == {"status": "success"}
    assert result["intraday"] == {
        "status": "failed",
        "reason": "baostock login failed: 10002007",
    }


def test_check_strategy_daily_eod_dependencies_includes_common_provider_error(monkeypatch):
    monkeypatch.setattr(
        eod,
        "_fetch_one",
        lambda *_args, **_kwargs: [
            {
                "daily_status": "failed",
                "minute5_status": "success",
                "deps_status": "success",
                "failed_jobs": [
                    {
                        "stage": "daily",
                        "source": "tushare",
                        "error_summary": "token rejected",
                    }
                ],
            }
        ],
    )

    result = eod.check_strategy_daily_eod_dependencies(trade_date="2026-06-24")

    assert result["common"] == {
        "status": "failed",
        "reason": "daily_status=failed: tushare token rejected",
    }
