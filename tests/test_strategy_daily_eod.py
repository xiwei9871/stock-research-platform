import importlib.util
from pathlib import Path

import pandas as pd

from stock_research import strategy_daily_eod as eod
from stock_research import strategy_daily_eod_store as store


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
    assert result["output_dir"].startswith(str(tmp_path / ".versions" / "2026-06-24"))
    assert result["manifest_modules"] == [
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "review_queue_strategy_manifest",
    ]
    assert captured["payload"]["status"] == "partial"


def test_official_strategy_runner_writes_task7_canonical_release(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda *_args, **_kwargs: None)
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
        lhb_runner=runner,
        mid_runner=runner,
        tech_runner=runner,
        midtrend_artifact_builder=artifact_builder,
    )

    assert result["status"] == "partial"
    assert result["strategy_status"]["midtrend_artifacts"] == "success"
    assert "midtrend_v2_top10_candidate.csv" in result["midtrend_artifacts"]
    assert captured["payload"]["status"] == "partial"


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

    def runner(name, rows):
        def run(*, trade_date, output_dir, service):
            calls.append(name)
            return {"status": "success", "review_rows": rows, "paths": {}}

        return run

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
        lhb_runner=runner("lhb", 99),
        mid_runner=runner("mid", 2),
        midtrend_artifact_builder=runner("midtrend_artifacts", 0),
        tech_runner=runner("tech", 3),
    )

    assert calls == ["mid", "midtrend_artifacts", "tech"]
    assert result["status"] == "partial"
    assert result["review_rows"] == 5
    assert result["strategy_status"] == {
        "lhb_shortline": "blocked",
        "mid_trend": "success",
        "midtrend_artifacts": "success",
        "tech_bottleneck": "success",
    }
    assert result["strategy_errors"]["lhb_shortline"] == "intraday: baostock login failed: 10002007"
    assert result["dependency_check"]["intraday"]["reason"] == "baostock login failed: 10002007"
    assert captured["payload"]["status"] == "partial"
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
        lhb_runner=success,
        mid_runner=failed,
        midtrend_artifact_builder=success,
        tech_runner=success,
    )

    assert result["status"] == "partial"
    assert result["strategy_status"]["mid_trend"] == "failed"
    assert result["strategy_errors"]["mid_trend"] == "model unavailable"


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
