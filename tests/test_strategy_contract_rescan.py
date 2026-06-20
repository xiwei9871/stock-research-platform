import pandas as pd

from stock_research.strategy_contracts import (
    StrategyContract,
    load_strategy_contracts,
    strategy_contract_run_config,
    validate_strategy_summary_against_contract,
)
from stock_research.strategy_contract_rescan import (
    load_lhb_scan_candidates,
    load_mid_trend_scan_candidates,
    load_tech_bottleneck_scan_candidates,
    run_official_strategy_contract_rescan,
    select_strategy_profiles,
)


def test_selects_return_balanced_and_drawdown_profiles() -> None:
    candidates = pd.DataFrame(
        [
            {
                "strategy_id": "mid_trend",
                "variant": "fast",
                "final_equity": 3.0,
                "total_return": 2.0,
                "max_drawdown": -0.35,
                "sharpe": 2.0,
                "trade_rows": 40,
                "position_rows": 80,
            },
            {
                "strategy_id": "mid_trend",
                "variant": "balanced",
                "final_equity": 2.5,
                "total_return": 1.5,
                "max_drawdown": -0.18,
                "sharpe": 2.8,
                "trade_rows": 35,
                "position_rows": 80,
            },
            {
                "strategy_id": "mid_trend",
                "variant": "defensive",
                "final_equity": 1.9,
                "total_return": 0.9,
                "max_drawdown": -0.08,
                "sharpe": 2.1,
                "trade_rows": 20,
                "position_rows": 70,
            },
        ]
    )

    profiles = select_strategy_profiles(candidates, strategy_id="mid_trend")

    assert profiles["return_first"]["variant"] == "fast"
    assert profiles["balanced"]["variant"] == "balanced"
    assert profiles["drawdown_first"]["variant"] == "defensive"


def test_mid_trend_balanced_prefers_risk_exit_variant_when_viable() -> None:
    candidates = pd.DataFrame(
        [
            {
                "strategy_id": "mid_trend",
                "variant": "top5_weekly_max_2_replacements",
                "top_n": 5,
                "final_equity": 1.45,
                "total_return": 0.45,
                "max_drawdown": -0.12,
                "sharpe": 2.8,
                "trade_rows": 92,
                "position_rows": 115,
            },
            {
                "strategy_id": "mid_trend",
                "variant": "top5_weekly_max2_selective_trend_holding_protection_v1",
                "top_n": 5,
                "final_equity": 1.35,
                "total_return": 0.35,
                "max_drawdown": -0.10,
                "sharpe": 2.6,
                "trade_rows": 185,
                "position_rows": 115,
            },
        ]
    )

    profiles = select_strategy_profiles(candidates, strategy_id="mid_trend")

    assert profiles["return_first"]["variant"] == "top5_weekly_max_2_replacements"
    assert profiles["balanced"]["variant"] == "top5_weekly_max2_selective_trend_holding_protection_v1"


def test_tech_bottleneck_balanced_prefers_top5_when_available() -> None:
    candidates = pd.DataFrame(
        [
            {
                "strategy_id": "tech_bottleneck",
                "variant": "strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
                "top_n": 3,
                "final_equity": 2.0,
                "total_return": 1.0,
                "max_drawdown": -0.10,
                "sharpe": 3.0,
                "trade_rows": 10,
                "position_rows": 10,
            },
            {
                "strategy_id": "tech_bottleneck",
                "variant": "strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
                "top_n": 5,
                "final_equity": 1.9,
                "total_return": 0.9,
                "max_drawdown": -0.09,
                "sharpe": 3.1,
                "trade_rows": 10,
                "position_rows": 10,
            },
        ]
    )

    profiles = select_strategy_profiles(candidates, strategy_id="tech_bottleneck")

    assert profiles["balanced"]["top_n"] == 5


def test_rejects_rows_without_real_strategy_artifacts() -> None:
    candidates = pd.DataFrame(
        [
            {
                "strategy_id": "lhb_shortline",
                "variant": "empty",
                "final_equity": 9.0,
                "max_drawdown": -0.01,
                "trade_rows": 0,
                "position_rows": 0,
            },
            {
                "strategy_id": "lhb_shortline",
                "variant": "real",
                "final_equity": 2.0,
                "max_drawdown": -0.10,
                "trade_rows": 10,
                "position_rows": 10,
            },
        ]
    )

    profiles = select_strategy_profiles(candidates, strategy_id="lhb_shortline")

    assert profiles["return_first"]["variant"] == "real"


def test_load_lhb_scan_candidates_normalizes_phase18c_summary(tmp_path) -> None:
    path = tmp_path / "lhb_phase18c_summary_v1.csv"
    pd.DataFrame(
        [
            {
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "final_equity": 2.7,
                "total_return": 1.7,
                "max_drawdown": -0.06,
                "sharpe_ratio": 3.1,
                "filled_trade_count": 120,
            }
        ]
    ).to_csv(path, index=False)

    rows = load_lhb_scan_candidates([path])

    assert rows.iloc[0]["strategy_id"] == "lhb_shortline"
    assert rows.iloc[0]["engine"] == "lhb_shortline_v1"
    assert rows.iloc[0]["variant"] == "auction_enhanced_rerank"
    assert rows.iloc[0]["top_n"] == 5
    assert rows.iloc[0]["trade_rows"] == 120
    assert rows.iloc[0]["benchmark_artifact_path"] == str(path)


def test_load_lhb_scan_candidates_includes_risk_profile_in_variant(tmp_path) -> None:
    path = tmp_path / "lhb_shortline_v1_profile_scan_summary.csv"
    pd.DataFrame(
        [
            {
                "strategy": "auction_enhanced_rerank",
                "risk_profile": "drawdown_control",
                "top_n": 5,
                "final_equity": 1.5,
                "max_drawdown": -0.02,
                "trade_rows": 20,
                "position_rows": 20,
            }
        ]
    ).to_csv(path, index=False)

    rows = load_lhb_scan_candidates([path])

    assert rows.iloc[0]["variant"] == "auction_enhanced_rerank:drawdown_control"


def test_select_strategy_profiles_prefers_explicit_profile_hint() -> None:
    candidates = pd.DataFrame(
        [
            {
                "strategy_id": "lhb_shortline",
                "variant": "auction_enhanced_rerank:return_max",
                "selected_profile_hint": "return_first",
                "final_equity": 1.68,
                "max_drawdown": -0.031,
                "trade_rows": 10,
                "position_rows": 10,
            },
            {
                "strategy_id": "lhb_shortline",
                "variant": "auction_enhanced_rerank:balanced",
                "selected_profile_hint": "balanced",
                "final_equity": 1.62,
                "max_drawdown": -0.027,
                "trade_rows": 10,
                "position_rows": 10,
            },
            {
                "strategy_id": "lhb_shortline",
                "variant": "auction_enhanced_rerank:drawdown_control",
                "selected_profile_hint": "drawdown_first",
                "final_equity": 1.56,
                "max_drawdown": -0.023,
                "trade_rows": 10,
                "position_rows": 10,
            },
        ]
    )

    profiles = select_strategy_profiles(candidates, strategy_id="lhb_shortline")

    assert profiles["return_first"]["variant"] == "auction_enhanced_rerank:return_max"
    assert profiles["balanced"]["variant"] == "auction_enhanced_rerank:balanced"
    assert profiles["drawdown_first"]["variant"] == "auction_enhanced_rerank:drawdown_control"


def test_balanced_profile_requires_75_percent_return_and_lower_drawdown() -> None:
    candidates = pd.DataFrame(
        [
            {
                "strategy_id": "tech_bottleneck",
                "variant": "return",
                "final_equity": 5.0,
                "total_return": 4.0,
                "max_drawdown": -0.20,
                "sharpe": 3.5,
                "trade_rows": 10,
                "position_rows": 10,
            },
            {
                "strategy_id": "tech_bottleneck",
                "variant": "too_low_return",
                "final_equity": 3.5,
                "total_return": 2.5,
                "max_drawdown": -0.10,
                "sharpe": 3.2,
                "trade_rows": 10,
                "position_rows": 10,
            },
            {
                "strategy_id": "tech_bottleneck",
                "variant": "balanced",
                "final_equity": 4.1,
                "total_return": 3.1,
                "max_drawdown": -0.15,
                "sharpe": 3.0,
                "trade_rows": 10,
                "position_rows": 10,
            },
        ]
    )

    profiles = select_strategy_profiles(candidates, strategy_id="tech_bottleneck")

    assert profiles["return_first"]["variant"] == "return"
    assert profiles["balanced"]["variant"] == "balanced"


def test_balanced_profile_does_not_accept_float_noise_drawdown_improvement() -> None:
    candidates = pd.DataFrame(
        [
            {
                "strategy_id": "mid_trend",
                "variant": "return",
                "final_equity": 2.0,
                "total_return": 1.0,
                "max_drawdown": -0.2541204617451228,
                "sharpe": 1.6,
                "trade_rows": 10,
                "position_rows": 10,
            },
            {
                "strategy_id": "mid_trend",
                "variant": "float_noise",
                "final_equity": 1.9,
                "total_return": 0.9,
                "max_drawdown": -0.2541204617451227,
                "sharpe": 1.5,
                "trade_rows": 10,
                "position_rows": 10,
            },
        ]
    )

    profiles = select_strategy_profiles(candidates, strategy_id="mid_trend")

    assert profiles["balanced"]["variant"] == "return"
    assert "no independent balanced candidate" in profiles["balanced"]["profile_selection_note"]


def test_load_mid_trend_scan_candidates_normalizes_weekly_summary(tmp_path) -> None:
    path = tmp_path / "mid_trend_shadow_weekly_control_summary.csv"
    pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1",
                "top_n": 5,
                "transaction_cost_bps": 20.0,
                "final_equity": 4.2,
                "total_return": 3.2,
                "max_drawdown": -0.22,
                "sharpe_ratio": 2.9,
                "trade_rows": 285,
                "position_rows": 360,
            }
        ]
    ).to_csv(path, index=False)

    rows = load_mid_trend_scan_candidates([path])

    assert rows.iloc[0]["strategy_id"] == "mid_trend"
    assert rows.iloc[0]["engine"] == "mid_trend_v1"
    assert rows.iloc[0]["variant"] == "top5_weekly_max2_selective_trend_holding_protection_v1"
    assert rows.iloc[0]["frequency"] == "weekly"
    assert rows.iloc[0]["transaction_cost_bps"] == 20.0


def test_load_tech_bottleneck_scan_candidates_normalizes_serenity_summary(tmp_path) -> None:
    path = tmp_path / "serenity_tight3b_c2_matrix_summary.csv"
    pd.DataFrame(
        [
            {
                "universe": "strict_153",
                "frequency": "weekly",
                "top_n": 5,
                "protection_name": "rank_exit_top10_1d",
                "total_return": 2.58,
                "max_drawdown": -0.17,
                "sharpe": 3.5,
            }
        ]
    ).to_csv(path, index=False)

    rows = load_tech_bottleneck_scan_candidates([path])

    assert rows.iloc[0]["strategy_id"] == "tech_bottleneck"
    assert rows.iloc[0]["engine"] == "tech_bottleneck_v1"
    assert rows.iloc[0]["variant"] == "strict_153:weekly:rank_exit_top10_1d"
    assert rows.iloc[0]["protection_name"] == "rank_exit_top10_1d"


def test_run_official_strategy_contract_rescan_writes_profile_outputs(tmp_path) -> None:
    lhb = tmp_path / "lhb_phase18c_summary_v1.csv"
    pd.DataFrame(
        [
            {"strategy": "auction_enhanced_rerank", "top_n": 5, "final_equity": 2.0, "max_drawdown": -0.10, "filled_trade_count": 10}
        ]
    ).to_csv(lhb, index=False)
    mid = tmp_path / "mid_trend_shadow_weekly_control_summary.csv"
    pd.DataFrame(
        [
            {
                "variant_name": "mid_balanced",
                "top_n": 5,
                "final_equity": 2.0,
                "max_drawdown": -0.10,
                "trade_rows": 10,
                "position_rows": 10,
            }
        ]
    ).to_csv(mid, index=False)
    tech = tmp_path / "serenity_tight3b_c2_matrix_summary.csv"
    pd.DataFrame(
        [
            {"universe": "strict_153", "frequency": "weekly", "top_n": 5, "protection_name": "rank_exit_top10_1d", "total_return": 1.0, "max_drawdown": -0.10}
        ]
    ).to_csv(tech, index=False)

    result = run_official_strategy_contract_rescan(
        output_dir=tmp_path / "out",
        lhb_paths=[lhb],
        mid_trend_paths=[mid],
        tech_bottleneck_paths=[tech],
    )

    assert result["candidate_count"] == 3
    assert result["paths"]["candidates"].endswith("official_strategy_profile_candidates.csv")
    assert result["paths"]["contracts"].endswith("official_strategy_contracts.json")
    selected = pd.read_csv(result["paths"]["candidates"])
    assert set(selected["strategy_id"]) == {"lhb_shortline", "mid_trend", "tech_bottleneck"}
    assert (tmp_path / "out" / "official_strategy_contract_rescan_report.md").exists()


def test_strategy_contract_rescan_cli_dispatches_runner(monkeypatch, capsys, tmp_path) -> None:
    from stock_research import cli

    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return {
            "candidate_count": 9,
            "paths": {
                "candidates": str(tmp_path / "candidates.csv"),
                "contracts": str(tmp_path / "contracts.json"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_official_strategy_contract_rescan", fake_runner)

    cli.main(
        [
            "rescan-official-strategy-contracts",
            "--output-dir",
            str(tmp_path),
            "--lhb-summary-path",
            str(tmp_path / "lhb.csv"),
            "--mid-trend-summary-path",
            str(tmp_path / "mid.csv"),
            "--tech-bottleneck-summary-path",
            str(tmp_path / "tech.csv"),
        ]
    )

    assert calls[0]["output_dir"] == str(tmp_path)
    assert calls[0]["lhb_paths"] == [tmp_path / "lhb.csv"]
    assert capsys.readouterr().out.splitlines() == [
        f"strategy_contract_rescan|summary|{tmp_path / 'candidates.csv'}",
        f"strategy_contract_rescan|contracts|{tmp_path / 'contracts.json'}",
        f"strategy_contract_rescan|report|{tmp_path / 'report.md'}",
        "strategy_contract_rescan|rows|9",
    ]


def test_contract_rejects_mismatched_variant() -> None:
    contract = StrategyContract(
        contract_id="mid_trend:balanced:v1",
        strategy_id="mid_trend",
        profile="balanced",
        engine="mid_trend_v1",
        variant="top5_weekly_max2_selective_trend_holding_protection_v1",
        top_n=5,
        transaction_cost_bps=20.0,
        adjust_type="hfq",
        frequency="weekly",
    )
    summary = {
        "engine_version": "mid_trend_v1",
        "variant_name": "other",
        "top_n": 5,
        "transaction_cost_bps": 10.0,
        "adjust_type": "hfq",
        "frequency": "weekly",
    }

    result = validate_strategy_summary_against_contract(summary, contract)

    assert result.status == "failed"
    assert "variant" in result.reason


def test_contract_accepts_matching_tech_bottleneck_summary() -> None:
    contract = StrategyContract(
        contract_id="tech_bottleneck:balanced:v1",
        strategy_id="tech_bottleneck",
        profile="balanced",
        engine="tech_bottleneck_v1",
        variant="strict_153:weekly:rank_exit_top10_1d",
        top_n=5,
        transaction_cost_bps=20.0,
        adjust_type="hfq",
        frequency="weekly",
        protection_name="rank_exit_top10_1d",
    )
    summary = {
        "engine_version": "tech_bottleneck_v1",
        "universe": "strict_153",
        "frequency": "weekly",
        "protection_name": "rank_exit_top10_1d",
        "top_n": 5,
        "transaction_cost_bps": 10.0,
        "adjust_type": "hfq",
    }

    result = validate_strategy_summary_against_contract(summary, contract)

    assert result.status == "success"
    assert result.reason == ""


def test_contract_accepts_matching_lhb_risk_profile_summary() -> None:
    contract = StrategyContract(
        contract_id="lhb_shortline:balanced:v1",
        strategy_id="lhb_shortline",
        profile="balanced",
        engine="lhb_shortline_v1",
        variant="auction_enhanced_rerank:balanced",
        top_n=5,
        transaction_cost_bps=10.0,
        adjust_type="qfq",
        frequency="daily",
    )
    summary = {
        "engine_version": "lhb_shortline_v1",
        "phase18c_strategy": "auction_enhanced_rerank",
        "risk_profile": "balanced",
        "top_n": 5,
        "transaction_cost_bps": 10.0,
        "adjust_type": "qfq",
        "frequency": "daily",
    }

    result = validate_strategy_summary_against_contract(summary, contract)

    assert result.status == "success"


def test_load_strategy_contracts_reads_balanced_profiles(tmp_path) -> None:
    path = tmp_path / "official_strategy_contracts.json"
    path.write_text(
        """
{
  "contract_version": "test",
  "profiles": [
    {
      "strategy_id": "lhb_shortline",
      "selected_profile": "balanced",
      "engine": "lhb_shortline_v1",
      "variant": "auction_enhanced_rerank:balanced",
      "top_n": 5,
      "frequency": "daily",
      "transaction_cost_bps": 10.0,
      "adjust_type": "qfq"
    },
    {
      "strategy_id": "tech_bottleneck",
      "selected_profile": "balanced",
      "engine": "tech_bottleneck_v1",
      "variant": "strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
      "top_n": 5,
      "frequency": "biweekly",
      "protection_name": "rank_exit_top10_1d",
      "transaction_cost_bps": 20.0,
      "adjust_type": "hfq"
    }
  ]
}
""",
        encoding="utf-8",
    )

    contracts = load_strategy_contracts(path, profile="balanced")

    assert contracts["lhb_shortline"].variant == "auction_enhanced_rerank:balanced"
    assert contracts["tech_bottleneck"].top_n == 5
    assert contracts["tech_bottleneck"].frequency == "biweekly"


def test_strategy_contract_run_config_maps_profiles_to_backend_payload() -> None:
    lhb = StrategyContract(
        contract_id="lhb_shortline:balanced:v1",
        strategy_id="lhb_shortline",
        profile="balanced",
        engine="lhb_shortline_v1",
        variant="auction_enhanced_rerank:balanced",
        top_n=5,
        frequency="daily",
        transaction_cost_bps=10.0,
        adjust_type="qfq",
    )
    tech = StrategyContract(
        contract_id="tech_bottleneck:balanced:v1",
        strategy_id="tech_bottleneck",
        profile="balanced",
        engine="tech_bottleneck_v1",
        variant="strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
        top_n=5,
        frequency="biweekly",
        protection_name="rank_exit_top10_1d",
        transaction_cost_bps=20.0,
        adjust_type="hfq",
    )

    assert strategy_contract_run_config(lhb) == {
        "top_n": 5,
        "rebalance_frequency": "daily",
        "transaction_cost_bps": 10.0,
        "max_position_weight": 0.2,
        "adjust_type": "qfq",
        "risk_profile": "balanced",
        "contract_id": "lhb_shortline:balanced:v1",
        "contract_profile": "balanced",
        "contract_variant": "auction_enhanced_rerank:balanced",
    }
    assert strategy_contract_run_config(tech)["rebalance_frequency"] == "biweekly"
    assert strategy_contract_run_config(tech)["top_n"] == 5
    assert strategy_contract_run_config(tech)["transaction_cost_bps"] == 10.0
    assert strategy_contract_run_config(tech)["max_position_weight"] == 0.2
