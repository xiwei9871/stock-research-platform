import pytest

import stock_research.eod_auto_repair_checks as eod_auto_repair_checks
from stock_research.eod_auto_repair_checks import (
    build_check_plan,
    check_factor_daily,
    check_lhb_features,
    check_dashboard_surface_freshness,
    check_strategy_score_audit,
    check_strategy_publish,
    evaluate_count_check,
    evaluate_review_queue_groups,
    evaluate_strategy_review_scores,
)
from stock_research.eod_auto_repair_models import RepairStatus
from stock_research.eod_browser_acceptance import REPORT_SCHEMA_VERSION


def _browser_manifest_row(**overrides):
    row = {
        "module": "dashboard_browser_acceptance",
        "source": "eod_browser_acceptance",
        "status": "success",
        "trade_date": "2026-06-29",
        "run_id": "strategy-eod-2026-06-29-local",
        "ended_at": "2026-06-29T09:00:00+00:00",
        "warnings": [],
        "artifact_path": "/tmp/eod-browser-acceptance.json",
        "metadata": {
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "application_revision": "abc123",
            "artifact_paths": [
                "/tmp/eod-browser-acceptance.json",
                "/tmp/trace.zip",
            ],
        },
    }
    row.update(overrides)
    return row


def test_evaluate_count_check_success_when_count_meets_minimum():
    result = evaluate_count_check(
        name="score_topn",
        row_count=5187,
        min_rows=1,
        latest_trade_date="2026-06-29",
        trade_date="2026-06-29",
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["row_count"] == 5187
    assert result.blocker is False


def test_evaluate_count_check_failed_when_latest_date_stale():
    result = evaluate_count_check(
        name="review_queue_strategy_manifest",
        row_count=10,
        min_rows=1,
        latest_trade_date="2026-06-26",
        trade_date="2026-06-29",
    )

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True
    assert "2026-06-26" in result.message


def test_build_check_plan_contains_required_gate_names():
    names = [check.name for check in build_check_plan("2026-06-29")]

    assert names == [
        "daily_bars",
        "minute5_bars",
        "lhb_source",
        "lhb_features",
        "technical_features",
        "factor_daily",
        "score_topn",
        "watchlist",
        "market_monitor",
        "strategy_publish",
        "review_queue",
        "strategy_score_audit",
        "reports",
        "review_evidence_snapshots",
        "dashboard_browser_acceptance",
        "dashboard_surface_freshness",
        "ops_health",
    ]

    ordered_gate_names = [
        name
        for name in names
        if name
        in {
            "strategy_publish",
            "dashboard_browser_acceptance",
            "dashboard_surface_freshness",
            "ops_health",
        }
    ]
    assert ordered_gate_names == [
        "strategy_publish",
        "dashboard_browser_acceptance",
        "dashboard_surface_freshness",
        "ops_health",
    ]


@pytest.mark.parametrize(
    ("manifest_status", "expected_status"),
    [("success", RepairStatus.SUCCESS), ("degraded", RepairStatus.DEGRADED)],
)
def test_check_dashboard_browser_acceptance_maps_publishable_latest_manifest(
    manifest_status,
    expected_status,
):
    older = _browser_manifest_row(
        run_id="older-run",
        ended_at="2026-06-29T08:00:00+00:00",
        status="failed",
    )
    latest = _browser_manifest_row(
        status=manifest_status,
        warnings=["console warning"] if manifest_status == "degraded" else [],
    )

    result = eod_auto_repair_checks.check_dashboard_browser_acceptance(
        "2026-06-29",
        manifest_loader=lambda trade_date: [older, latest],
    )

    assert result.status == expected_status
    assert result.blocker is False
    assert result.metrics["run_id"] == latest["run_id"]
    assert result.metrics["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert result.metrics["artifact_paths"] == latest["metadata"]["artifact_paths"]
    assert result.metrics["warnings"] == latest["warnings"]


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_browser_manifest_row(status="failed")],
        [_browser_manifest_row(trade_date="2026-06-28")],
        [
            _browser_manifest_row(
                metadata={
                    "report_schema_version": "playwright-eod-browser-acceptance/v0",
                    "application_revision": "abc123",
                    "artifact_paths": [],
                }
            )
        ],
        [_browser_manifest_row(metadata="malformed")],
        [_browser_manifest_row(run_id="")],
    ],
)
def test_check_dashboard_browser_acceptance_fails_closed_for_invalid_manifest(rows):
    result = eod_auto_repair_checks.check_dashboard_browser_acceptance(
        "2026-06-29",
        manifest_loader=lambda trade_date: rows,
    )

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True


def test_check_dashboard_browser_acceptance_fails_closed_when_latest_record_is_ambiguous():
    rows = [
        _browser_manifest_row(),
        _browser_manifest_row(status="degraded", warnings=["different result"]),
    ]

    result = eod_auto_repair_checks.check_dashboard_browser_acceptance(
        "2026-06-29",
        manifest_loader=lambda trade_date: rows,
    )

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True
    assert "ambiguous" in result.message


def test_check_lhb_features_reads_factor_table_with_fetcher():
    captured = {}

    def fetcher(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [{"row_count": 102, "asset_count": 102, "latest_trade_date": "2026-06-29"}]

    result = check_lhb_features("2026-06-29", fetcher=fetcher)

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["asset_count"] == 102
    assert "factor.lhb_event_features_daily" in captured["sql"]
    assert captured["params"] == ["2026-06-29"]


def test_check_factor_daily_requires_rows_for_trade_date():
    rows = [
        {
            "row_count": 194997,
            "asset_count": 5187,
            "factor_count": 41,
            "latest_trade_date": "2026-07-01",
        }
    ]

    result = check_factor_daily("2026-07-01", fetcher=lambda sql, params: rows)

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["row_count"] == 194997
    assert result.metrics["asset_count"] == 5187
    assert result.metrics["factor_count"] == 41


def test_check_factor_daily_marks_empty_date_blocking():
    rows = [{"row_count": 0, "asset_count": 0, "factor_count": 0, "latest_trade_date": ""}]

    result = check_factor_daily("2026-07-01", fetcher=lambda sql, params: rows)

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True


def test_check_strategy_publish_requires_three_strategy_modules_and_manifest():
    rows = [
        {
            "module": "strategy_lhb_shortline",
            "status": "success",
            "row_count": 4,
            "asset_count": 4,
            "latest_trade_date": "2026-06-29",
        },
        {
            "module": "strategy_mid_trend",
            "status": "success",
            "row_count": 5,
            "asset_count": 5,
            "latest_trade_date": "2026-06-29",
        },
        {
            "module": "strategy_tech_bottleneck",
            "status": "success",
            "row_count": 5,
            "asset_count": 5,
            "latest_trade_date": "2026-06-29",
        },
        {
            "module": "review_queue_strategy_manifest",
            "status": "success",
            "row_count": 14,
            "asset_count": 14,
            "latest_trade_date": "2026-06-29",
        },
    ]

    result = check_strategy_publish("2026-06-29", manifest_loader=lambda trade_date: rows)

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["strategy_ready"] == "3/3"
    assert result.metrics["review_rows"] == 14


def test_check_strategy_publish_degrades_when_strategy_performance_is_stale():
    rows = [
        {
            "module": "strategy_lhb_shortline",
            "status": "success",
            "row_count": 4,
            "asset_count": 4,
            "latest_trade_date": "2026-06-29",
            "metadata": {"summary": {"performance_effective_date": "2026-06-26"}},
        },
        {
            "module": "strategy_mid_trend",
            "status": "success",
            "row_count": 5,
            "asset_count": 5,
            "latest_trade_date": "2026-06-29",
            "metadata": {"summary": {"performance_effective_date": "2026-06-29"}},
        },
        {
            "module": "strategy_tech_bottleneck",
            "status": "success",
            "row_count": 5,
            "asset_count": 5,
            "latest_trade_date": "2026-06-29",
            "metadata": {"summary": {"performance_effective_date": "2026-06-29"}},
        },
        {
            "module": "review_queue_strategy_manifest",
            "status": "success",
            "row_count": 14,
            "asset_count": 14,
            "latest_trade_date": "2026-06-29",
        },
    ]

    result = check_strategy_publish("2026-06-29", manifest_loader=lambda trade_date: rows)

    assert result.status == RepairStatus.DEGRADED
    assert result.blocker is False
    assert result.metrics["stale_performance_modules"] == ["strategy_lhb_shortline:2026-06-26"]


def test_check_strategy_score_audit_fails_stale_source_anomalies():
    result = check_strategy_score_audit(
        "2026-06-29",
        summary_loader=lambda trade_date: {
            "trade_date": "2026-06-29",
            "status": "success",
            "anomaly_row_count": 3,
            "anomaly_counts_by_type": {"stale_source": 3},
        },
    )

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True
    assert result.metrics["anomaly_counts_by_type"] == {"stale_source": 3}


def test_check_dashboard_surface_freshness_catches_visible_stale_points():
    result = check_dashboard_surface_freshness(
        "2026-06-29",
        readiness_loader=lambda trade_date: {
            "display_trade_date": "2026-06-29",
            "latest_trade_date": "2026-06-29",
            "health_groups": [],
        },
        ops_snapshot_loader=lambda trade_date: {
            "run_window": {
                "requested_trade_date": "2026-06-30",
                "status_trade_date": "2026-06-29",
            },
            "readiness": {"ready_status": "not_ready", "blocking_issue_count": 3},
        },
        score_audit_loader=lambda trade_date: {
            "trade_date": "2026-06-29",
            "anomaly_row_count": 3,
            "anomaly_counts_by_type": {"stale_source": 3},
        },
        strategies_loader=lambda: [
            {
                "strategy_id": "lhb_shortline",
                "latest_metrics": {
                    "signal_as_of_date": "2026-06-29",
                    "performance_status": "stale",
                    "performance_as_of_date": "2026-06-26",
                },
            }
        ],
    )

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True
    assert "ops_snapshot:requested_trade_date=2026-06-30" in result.metrics["issues"]
    assert "strategy_score_audit:anomaly_row_count=3" in result.metrics["issues"]
    assert "backtests:lhb_shortline:performance_stale:2026-06-26" in result.metrics["issues"]


def test_check_dashboard_surface_freshness_degrades_display_lag_when_underlying_date_is_ready():
    result = check_dashboard_surface_freshness(
        "2026-07-01",
        readiness_loader=lambda trade_date: {
            "status": "OK",
            "display_trade_date": "2026-06-30",
            "latest_trade_date": "2026-07-01",
            "latest_market_date": "2026-07-01",
            "health_groups": [],
        },
        ops_snapshot_loader=lambda trade_date: {
            "run_window": {
                "requested_trade_date": "2026-07-01",
                "status_trade_date": "2026-07-01",
            },
            "readiness": {"ready_status": "degraded_ready", "blocking_issue_count": 0},
        },
        score_audit_loader=lambda trade_date: {
            "trade_date": "2026-07-01",
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
        },
        strategies_loader=lambda: [],
    )

    assert result.status == RepairStatus.DEGRADED
    assert result.blocker is False
    assert "readiness:display_trade_date=2026-06-30" in result.metrics["degraded_issues"]


def test_check_dashboard_surface_freshness_degrades_when_dashboard_has_advanced_past_trade_date():
    result = check_dashboard_surface_freshness(
        "2026-07-01",
        readiness_loader=lambda trade_date: {
            "status": "BLOCKED",
            "display_trade_date": "2026-06-30",
            "latest_trade_date": "2026-07-02",
            "latest_market_date": "2026-07-02",
            "health_groups": [
                {"items": [{"key": "market_monitor", "status": "missing_data"}]},
            ],
        },
        ops_snapshot_loader=lambda trade_date: {
            "run_window": {
                "requested_trade_date": "2026-07-01",
                "status_trade_date": "2026-07-01",
            },
            "readiness": {"ready_status": "degraded_ready", "blocking_issue_count": 0},
        },
        score_audit_loader=lambda trade_date: {
            "trade_date": "2026-07-01",
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
        },
        strategies_loader=lambda: [],
    )

    assert result.status == RepairStatus.DEGRADED
    assert result.blocker is False
    assert "readiness:latest_trade_date=2026-07-02" in result.metrics["degraded_issues"]
    assert "readiness:market_monitor:missing_data" in result.metrics["degraded_issues"]


def test_evaluate_review_queue_groups_fails_identical_lhb_and_midtrend_assets():
    payload = {
        "trade_date": "2026-06-29",
        "groups": [
            {"bucket": "strategy:lhb_shortline", "count": 2, "items": [{"asset_id": "A"}, {"asset_id": "B"}]},
            {"bucket": "strategy:mid_trend", "count": 2, "items": [{"asset_id": "A"}, {"asset_id": "B"}]},
            {"bucket": "strategy:tech_bottleneck", "count": 1, "items": [{"asset_id": "C"}]},
        ],
    }

    result = evaluate_review_queue_groups(payload, trade_date="2026-06-29")

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True
    assert "identical" in result.message


def test_evaluate_review_queue_groups_fails_zero_tech_bottleneck_count():
    payload = {
        "trade_date": "2026-06-29",
        "groups": [
            {"bucket": "strategy:lhb_shortline", "count": 4, "items": [{"asset_id": "A"}]},
            {"bucket": "strategy:mid_trend", "count": 5, "items": [{"asset_id": "B"}]},
            {"bucket": "strategy:tech_bottleneck", "count": 0, "items": []},
        ],
    }

    result = evaluate_review_queue_groups(payload, trade_date="2026-06-29")

    assert result.status == RepairStatus.FAILED
    assert "tech_bottleneck" in result.message


def test_evaluate_strategy_review_scores_fails_null_scores():
    rows = [
        {"strategy_id": "mid_trend", "asset_id": "CN:SH:603733", "score_total": None, "score_source": ""},
    ]

    result = evaluate_strategy_review_scores(rows, trade_date="2026-06-29")

    assert result.status == RepairStatus.FAILED
    assert result.metrics["null_score_rows"] == 1
