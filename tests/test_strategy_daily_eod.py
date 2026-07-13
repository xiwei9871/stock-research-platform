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

    summary_path = tmp_path / "2026-06-24" / "strategy_daily_eod_legacy" / "strategy_eod_publish_summary.json"
    assert result["status"] == "success"
    assert summary_path.exists()
    assert official_manifest.read_text(encoding="utf-8") == "official dashboard manifest\n"
    assert official_lhb.read_text(encoding="utf-8") == "official lhb\n"
    assert official_mid.read_text(encoding="utf-8") == "official mid\n"
    assert official_tech.read_text(encoding="utf-8") == "official tech\n"
    assert (tmp_path / "2026-06-24" / "strategy_daily_eod_legacy" / "strategy_daily_eod_review_manifest.csv").exists()
    assert result["output_dir"].endswith("strategy_daily_eod_legacy")
    assert captured["payload"]["status"] == "success"


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

    assert result["status"] == "success"
    assert result["strategy_status"]["midtrend_artifacts"] == "success"
    assert "midtrend_v2_top10_candidate.csv" in result["midtrend_artifacts"]
    assert captured["payload"]["status"] == "success"


def test_run_strategy_daily_eod_skips_when_deps_fail(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda payload, **_kwargs: captured.update(payload=payload))

    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "failed", "reason": "deps missing"},
    )

    assert result["status"] == "failed"
    assert result["strategy_status"]["lhb_shortline"] == "skipped"
    assert captured["payload"]["dependency_check_status"] == "failed"
