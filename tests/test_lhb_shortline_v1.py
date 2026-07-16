import pandas as pd
import pytest

from stock_research import lhb_shortline_v1
from stock_research.dashboard.strategy_backtest_adapters import build_lhb_shortline_scores_from_frames


def _candidate_frames(*, high_to_close_drawdown: float, pump_risk: float = 0.20):
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": "000001.SZ",
                "asset_id": "CN:SZ:000001",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.10,
                "lhb_net_buy_amount": 100_000_000.0,
                "institution_net_buy": 20_000_000.0,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": pump_risk,
            }
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": "000001.SZ",
                "asset_id": "CN:SZ:000001",
                "amount_vs_20d": 1.0,
                "high_to_close_drawdown": high_to_close_drawdown,
            }
        ]
    )
    return lhb, technical


def test_candidate_score_penalizes_positive_high_to_close_drawdown():
    base_lhb, base_tech = _candidate_frames(high_to_close_drawdown=0.0)
    faded_lhb, faded_tech = _candidate_frames(high_to_close_drawdown=0.10)

    base = lhb_shortline_v1.build_lhb_shortline_v1_candidates(base_lhb, base_tech, candidate_pool_n=10)
    faded = lhb_shortline_v1.build_lhb_shortline_v1_candidates(faded_lhb, faded_tech, candidate_pool_n=10)

    assert faded.iloc[0]["score_total"] == pytest.approx(base.iloc[0]["score_total"] - 4.0)


def test_pump_warning_band_is_not_rejected_by_candidate_or_dashboard_adapter():
    lhb, technical = _candidate_frames(high_to_close_drawdown=0.02, pump_risk=0.80)

    candidates = lhb_shortline_v1.build_lhb_shortline_v1_candidates(lhb, technical, candidate_pool_n=10)
    dashboard = build_lhb_shortline_scores_from_frames(lhb, technical)

    assert candidates["ts_code"].tolist() == ["000001.SZ"]
    assert dashboard.iloc[0]["eligibility"] is True


def test_lifecycle_contract_filter_keeps_only_entry_eligible_rows():
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": "ELIGIBLE.SZ",
                "eligibility_status": "eligible",
                "backtest_entry_eligible": True,
                "eligibility_contract_version": "lhb_eligibility_v2",
            },
            {
                "trade_date": "2026-07-14",
                "ts_code": "RISK.SZ",
                "eligibility_status": "risk_watch",
                "backtest_entry_eligible": False,
                "eligibility_contract_version": "lhb_eligibility_v2",
            },
            {
                "trade_date": "2026-07-14",
                "ts_code": "REJECT.SZ",
                "eligibility_status": "hard_reject",
                "backtest_entry_eligible": False,
                "eligibility_contract_version": "lhb_eligibility_v2",
            },
        ]
    )

    result = lhb_shortline_v1._filter_lhb_entry_eligible_contract_rows(candidates, stage="test_candidates")

    assert result["ts_code"].tolist() == ["ELIGIBLE.SZ"]


@pytest.mark.parametrize(
    "invalid",
    [
        {"backtest_entry_eligible": True},
        {
            "backtest_entry_eligible": True,
            "eligibility_contract_version": "lhb_eligibility_v1",
        },
    ],
)
def test_lifecycle_contract_assertion_rejects_missing_or_mismatched_version(invalid):
    frame = pd.DataFrame([{"trade_date": "2026-07-14", "ts_code": "000001.SZ", **invalid}])

    with pytest.raises(ValueError, match="LHB eligibility parity violation"):
        lhb_shortline_v1._assert_lhb_entry_eligibility_contract(frame, stage="account_entry")


def test_contract_propagation_rejects_contradictory_downstream_decision_and_audits_matches():
    source = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": "000001.SZ",
                "eligibility_status": "eligible",
                "backtest_entry_eligible": True,
                "eligibility_contract_version": "lhb_eligibility_v2",
            }
        ]
    )
    downstream = pd.DataFrame(
        [{"trade_date": "2026-07-14", "ts_code": "000001.SZ", "fill_status": "filled"}]
    )
    propagated = lhb_shortline_v1._attach_lhb_contract_decisions(
        downstream,
        decisions=source,
        stage="account",
    )
    audit = lhb_shortline_v1._build_lhb_eligibility_parity_audit(
        decisions=source,
        stages={"account": propagated},
    )

    assert audit.iloc[0]["parity_status"] == "match"
    contradictory = downstream.assign(eligibility_status="risk_watch")
    with pytest.raises(ValueError, match="contradictory eligibility_status"):
        lhb_shortline_v1._attach_lhb_contract_decisions(
            contradictory,
            decisions=source,
            stage="account",
        )


def test_parity_audit_treats_legitimate_downstream_attrition_as_not_observed():
    source = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": "000001.SZ",
                "eligibility_status": "eligible",
                "eligibility_contract_version": "lhb_eligibility_v2",
            }
        ]
    )

    audit = lhb_shortline_v1._build_lhb_eligibility_parity_audit(
        decisions=source,
        stages={"account": pd.DataFrame()},
    )

    assert audit.iloc[0]["parity_status"] == "match"


def test_review_candidates_keep_t_plus_one_confirmation_without_becoming_account_fill():
    scored = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-08",
                "entry_trade_date": "2026-07-09",
                "ts_code": "300017.SZ",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "auction_enhanced_score": 100.0,
                "eligibility_status": "eligible",
            }
        ]
    )

    review = lhb_shortline_v1._build_lhb_review_candidates(
        scored_candidates=scored,
        risk_watch_candidates=pd.DataFrame(),
        top_n=5,
    )

    assert review["ts_code"].tolist() == ["300017.SZ"]
    assert review.iloc[0]["phase12a_rule_layer"] == "follow_pool_core"


def test_build_lhb_review_candidates_keeps_only_eligible_original_top5_without_refill():
    scored = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-15",
                "ts_code": ts_code,
                "top_n": 5,
                "selection_rank": rank,
                "auction_enhanced_score": 100.0 - rank,
                "eligibility_status": "eligible",
                "backtest_entry_eligible": True,
            }
            for rank, ts_code in [(1, "000001.SZ"), (3, "000003.SZ"), (5, "000005.SZ"), (6, "000006.SZ")]
        ]
    )
    risk_watch = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-15",
                "ts_code": "000002.SZ",
                "selection_rank": 2,
                "eligibility_status": "risk_watch",
                "backtest_entry_eligible": False,
            }
        ]
    )

    review = lhb_shortline_v1._build_lhb_review_candidates(
        scored_candidates=scored,
        risk_watch_candidates=risk_watch,
        top_n=5,
    )

    assert review["selection_rank"].tolist() == [1, 3, 5]
    assert review["ts_code"].tolist() == ["000001.SZ", "000003.SZ", "000005.SZ"]
    assert review["eligibility_status"].eq("eligible").all()


def test_lhb_lifecycle_keeps_legacy_top10_research_pool_for_top5_account():
    assert lhb_shortline_v1._lhb_shortline_v1_top_values(5) == [10]


def test_minute_prefetch_uses_shared_pump_reject_threshold(monkeypatch):
    monkeypatch.setattr(lhb_shortline_v1, "PUMP_REJECT_THRESHOLD", 0.80)
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": "000001.SZ",
                "lhb_net_buy_amount": 1_000.0,
                "lhb_net_buy_ratio": 0.10,
                "institution_net_buy": 1.0,
                "top_seat_concentration": 0.10,
                "repeat_on_list_count_3d": 1,
                "lhb_one_day_pump_risk": 0.85,
                "lhb_after_limit_up": False,
                "lhb_after_break_limit": False,
            }
        ]
    )

    assert lhb_shortline_v1._minute_asset_ids_for_lhb_shortline_v1(features, [5]) == []


def test_cash_account_summary_uses_curve_end_as_performance_effective_date():
    account_trades = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "exit_trade_date": "2026-06-26",
                "realized_return": 0.1,
                "pnl": 0.02,
                "position_notional": 0.2,
            }
        ]
    )
    account_curve = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-26",
                "equity": 1.02,
                "drawdown": 0.0,
                "open_position_count": 0,
            },
            {
                "trade_date": "2026-06-29",
                "equity": 1.02,
                "drawdown": 0.0,
                "open_position_count": 0,
            },
        ]
    )

    summary = lhb_shortline_v1._summarize_lhb_shortline_market_regime_account(
        account_trades=account_trades,
        account_curve=account_curve,
    )

    assert summary["actual_end_date"] == "2026-06-29"
    assert summary["performance_effective_date"] == "2026-06-29"
    assert summary["latest_closed_trade_date"] == "2026-06-26"
