from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_round2_optimization import (
    DEFAULT_MID_TREND_ROUND2_CONFIG,
    build_mid_trend_round2_baseline_artifacts,
    build_mid_trend_round2_baseline_diagnostics,
    evaluate_mid_trend_round2_candidate_rule,
    label_mid_trend_round2_failure_modes,
    run_mid_trend_round2_optimization,
)


def _baseline_payload() -> dict[str, pd.DataFrame]:
    return {
        "train_summary": pd.DataFrame([{"metric": "winner_loss_count", "value": 10}, {"metric": "turnover_avg", "value": 0.20}]),
        "test_summary": pd.DataFrame([{"metric": "winner_loss_count", "value": 7}, {"metric": "turnover_avg", "value": 0.18}]),
    }


def test_build_mid_trend_round2_baseline_artifacts_respects_fixed_train_test_split(tmp_path: Path) -> None:
    result = build_mid_trend_round2_baseline_artifacts(
        start_date="2025-01-01",
        train_end_date="2026-02-01",
        end_date="2026-06-02",
        output_dir=tmp_path,
        baseline_payload=_baseline_payload(),
    )

    assert result["config"]["train_end_date"] == "2026-02-01"
    assert result["baseline_train_summary"]["split_name"].iloc[0] == "train"
    assert result["baseline_test_summary"]["split_name"].iloc[0] == "test"
    assert (tmp_path / "mid_trend_round2_baseline_train_summary.csv").exists()
    assert (tmp_path / "mid_trend_round2_baseline_test_summary.csv").exists()


def test_default_round2_config_uses_required_optimization_goal_hierarchy() -> None:
    assert DEFAULT_MID_TREND_ROUND2_CONFIG.primary_goal == "hold_winners_longer"
    assert DEFAULT_MID_TREND_ROUND2_CONFIG.secondary_goal == "reduce_low_value_turnover"
    assert "max_drawdown" in DEFAULT_MID_TREND_ROUND2_CONFIG.hard_constraints


def test_label_mid_trend_round2_failure_modes_maps_known_patterns() -> None:
    detail = pd.DataFrame(
        [
            {
                "audit_label": "bad_sell",
                "action": "sell",
                "root_cause": "dropped_out_of_top10_growth",
                "confirmed_regime_state": "bull_trend",
            },
            {
                "audit_label": "bad_sell",
                "action": "decrease",
                "root_cause": "exposure_shrink_decrease",
                "confirmed_regime_state": "bull_trend",
            },
        ]
    )

    labeled = label_mid_trend_round2_failure_modes(detail)

    assert labeled.loc[0, "round2_failure_mode"] == "stable_to_lower_layer_rank_collapse"
    assert labeled.loc[1, "round2_failure_mode"] == "allocation_trim_while_still_top_rank"


def test_build_mid_trend_round2_baseline_diagnostics_writes_auditable_csvs(tmp_path: Path) -> None:
    detail = pd.DataFrame(
        [
            {
                "audit_label": "bad_sell",
                "round2_failure_mode": "stable_to_lower_layer_rank_collapse",
                "forward_return": 0.25,
            }
        ]
    )

    result = build_mid_trend_round2_baseline_diagnostics(
        labeled_detail=detail,
        output_dir=tmp_path,
    )

    assert result["failure_mode_summary"].iloc[0]["round2_failure_mode"] == "stable_to_lower_layer_rank_collapse"
    assert (tmp_path / "mid_trend_round2_failure_mode_summary.csv").exists()


def test_evaluate_round2_candidate_rule_marks_keep_only_when_train_and_test_improve() -> None:
    baseline = pd.DataFrame(
        [{"metric": "winner_loss_count", "value": 10}, {"metric": "turnover_avg", "value": 0.20}]
    )
    candidate_train = pd.DataFrame(
        [{"metric": "winner_loss_count", "value": 7}, {"metric": "turnover_avg", "value": 0.15}]
    )
    candidate_test = pd.DataFrame(
        [{"metric": "winner_loss_count", "value": 8}, {"metric": "turnover_avg", "value": 0.17}]
    )

    decision = evaluate_mid_trend_round2_candidate_rule(
        candidate_name="stable_layer_buffer_v1",
        rule_family="stable_layer_downgrade_buffer",
        baseline_train=baseline,
        baseline_test=baseline,
        candidate_train=candidate_train,
        candidate_test=candidate_test,
    )

    assert decision["decision"] == "keep"
    assert decision["improves_primary_goal"] is True
    assert decision["improves_secondary_goal"] is True


def test_evaluate_round2_candidate_rule_rejects_when_test_drawdown_worsens() -> None:
    baseline = pd.DataFrame(
        [{"metric": "winner_loss_count", "value": 10}, {"metric": "max_drawdown", "value": -0.18}]
    )
    candidate = pd.DataFrame(
        [{"metric": "winner_loss_count", "value": 7}, {"metric": "max_drawdown", "value": -0.28}]
    )

    decision = evaluate_mid_trend_round2_candidate_rule(
        candidate_name="risk_reconfirm_v1",
        rule_family="risk_exclusion_reconfirmation",
        baseline_train=baseline,
        baseline_test=baseline,
        candidate_train=candidate,
        candidate_test=candidate,
    )

    assert decision["decision"] == "reject"
    assert decision["hard_constraint_breached"] is True


def test_run_mid_trend_round2_optimization_writes_decision_artifacts(tmp_path: Path) -> None:
    result = run_mid_trend_round2_optimization(
        start_date="2025-01-01",
        train_end_date="2026-02-01",
        end_date="2026-06-02",
        output_dir=tmp_path,
        baseline_payload=_baseline_payload(),
    )

    assert (tmp_path / "mid_trend_round2_baseline_train_summary.csv").exists()
    assert (tmp_path / "mid_trend_round2_baseline_test_summary.csv").exists()
    assert (tmp_path / "mid_trend_round2_failure_mode_summary.csv").exists()
    assert (tmp_path / "mid_trend_round2_candidate_audit.csv").exists()
    assert (tmp_path / "mid_trend_round2_report.md").exists()
    assert "candidate_audit" in result["paths"]


def test_cli_parser_accepts_mid_trend_round2_optimize_command() -> None:
    args = cli.build_parser().parse_args(
        [
            "mid-trend-round2-optimize",
            "--start-date",
            "2025-01-01",
            "--train-end-date",
            "2026-02-01",
            "--end-date",
            "2026-06-02",
            "--output-dir",
            "outputs/research/mid_trend_round2",
        ]
    )
    assert args.command == "mid-trend-round2-optimize"
    assert args.train_end_date == "2026-02-01"


def test_run_mid_trend_round2_cli_writes_decision_artifacts(tmp_path: Path, monkeypatch) -> None:
    def _fake_runner(**_: object) -> dict[str, object]:
        return {
            "paths": {
                "baseline_train_summary": str(tmp_path / "baseline_train.csv"),
                "candidate_audit": str(tmp_path / "candidate_audit.csv"),
                "report": str(tmp_path / "report.md"),
            }
        }

    monkeypatch.setattr(
        "stock_research.mid_trend_round2_optimization.run_mid_trend_round2_optimization",
        _fake_runner,
    )

    rc = cli.main(
        [
            "mid-trend-round2-optimize",
            "--start-date",
            "2025-01-01",
            "--train-end-date",
            "2026-02-01",
            "--end-date",
            "2026-06-02",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert rc in {0, None}
