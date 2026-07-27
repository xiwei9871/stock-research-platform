import errno
import importlib.util
import json
import os
from pathlib import Path

import pandas as pd

from stock_research import strategy_daily_eod as eod
from stock_research import strategy_daily_eod_store as store


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
    assert summary["status"] == "success"
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
        collected[0]["artifact_path"] = str(tmp_path / "escape.csv")
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
    assert "escapes staged release" in summary["error_summary"]
    assert (canonical / "marker").read_text(encoding="utf-8") == "old"


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
        tech_bottleneck_status="skipped",
        review_rows=0,
        output_dir="/tmp/out",
        summary_path="/tmp/out/summary.json",
        error_summary="deps missing",
    )

    assert payload["trade_date"] == "2026-06-24"
    assert payload["mid_trend_status"] == "skipped"
    assert "ops.strategy_daily_eod_status" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "'partial'" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "'blocked'" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "pg_get_constraintdef" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "IF constraint_definition IS NULL" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert store.STRATEGY_DAILY_EOD_STATUS_SQL.index(
        "IF constraint_definition IS NULL"
    ) < store.STRATEGY_DAILY_EOD_STATUS_SQL.index("DROP CONSTRAINT IF EXISTS")


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
        lhb_runner=runner,
        mid_runner=runner,
        tech_runner=runner,
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
    original_switch = eod._atomic_publish_directory
    switch_observations = []

    def observed_switch(staging, canonical):
        switch_observations.append((canonical / "old_release.marker").read_text(encoding="utf-8"))
        original_switch(staging, canonical)

    monkeypatch.setattr(eod, "_atomic_publish_directory", observed_switch)

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
        lhb_runner=runner_for("lhb_shortline", "strategy_lhb_shortline_review.csv"),
        mid_runner=runner_for("mid_trend", "strategy_mid_trend_review.csv"),
        tech_runner=runner_for("tech_bottleneck", "strategy_tech_bottleneck_review.csv"),
        midtrend_artifact_builder=lambda **_kwargs: {
            "status": "success",
            "review_rows": 0,
            "paths": {},
        },
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
        lhb_runner=runner,
        mid_runner=runner,
        tech_runner=runner,
        midtrend_artifact_builder=artifact_builder,
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
        lhb_runner=runner("lhb"),
        mid_runner=runner("mid"),
        midtrend_artifact_builder=runner("midtrend_artifacts"),
        tech_runner=runner("tech"),
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
        lhb_runner=success,
        mid_runner=failed,
        midtrend_artifact_builder=success,
        tech_runner=success,
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
