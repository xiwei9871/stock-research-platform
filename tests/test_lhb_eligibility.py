import pytest

from stock_research.lhb_eligibility import PriceLimitState, evaluate_lhb_eligibility, resolve_price_limit_state


def main_board_state(*, pct_chg: float) -> PriceLimitState:
    return PriceLimitState(
        regime="main_board",
        near_limit_down_threshold=-9.5,
        near_limit_down=pct_chg <= -9.5,
        is_st=False,
        status_source="same_day_lhb_name",
        data_quality_status="complete",
        pct_chg=pct_chg,
    )


@pytest.mark.parametrize(
    ("ts_code", "same_day_name", "pct_chg", "expected_regime", "expected_threshold"),
    [
        ("001399.SZ", "惠科股份", -9.5, "main_board", -9.5),
        ("000078.SZ", "ST海王", -4.8, "st", -4.8),
        ("300001.SZ", "特锐德", -19.0, "chinext", -19.0),
        ("688001.SH", "华兴源创", -19.0, "star", -19.0),
        ("920001.BJ", "北交样本", -29.0, "beijing", -29.0),
    ],
)
def test_resolve_price_limit_state_uses_same_day_regime(
    ts_code,
    same_day_name,
    pct_chg,
    expected_regime,
    expected_threshold,
):
    state = resolve_price_limit_state(
        trade_date="2026-07-14",
        ts_code=ts_code,
        same_day_name=same_day_name,
        current_name="当前名称不应决定历史状态",
        pct_chg=pct_chg,
        stored_is_st=None,
        stored_status_quality="untrusted_all_false",
        list_date="2020-01-01",
        listing_age_trading_days=100,
    )

    assert state.regime == expected_regime
    assert state.near_limit_down_threshold == expected_threshold
    assert state.status_source == "same_day_lhb_name"


def test_resolve_price_limit_state_marks_missing_price_change_unknown():
    state = resolve_price_limit_state(
        trade_date="2026-07-14",
        ts_code="001399.SZ",
        same_day_name="惠科股份",
        current_name="惠科股份",
        pct_chg=None,
        stored_is_st=False,
        stored_status_quality="trusted",
        list_date="2020-01-01",
        listing_age_trading_days=100,
    )

    assert state.data_quality_status == "pct_chg_missing"
    assert state.near_limit_down is False


def test_resolve_price_limit_state_ignores_current_st_name_for_history():
    state = resolve_price_limit_state(
        trade_date="2026-01-05",
        ts_code="600001.SH",
        same_day_name="示例股份",
        current_name="*ST示例",
        pct_chg=-5.0,
        stored_is_st=False,
        stored_status_quality="trusted",
        list_date="2010-01-01",
        listing_age_trading_days=100,
    )

    assert state.regime == "main_board"
    assert state.is_st is False
    assert state.status_source == "same_day_lhb_name"


def test_resolve_price_limit_state_marks_recent_listing_no_limit():
    state = resolve_price_limit_state(
        trade_date="2026-07-14",
        ts_code="001399.SZ",
        same_day_name="惠科股份",
        current_name="惠科股份",
        pct_chg=-20.0,
        stored_is_st=False,
        stored_status_quality="trusted",
        list_date="2026-07-10",
        listing_age_trading_days=3,
    )

    assert state.regime == "listing_no_limit"
    assert state.near_limit_down_threshold is None
    assert state.near_limit_down is False


def test_delisting_is_hard_reject_and_wins_over_other_rules():
    decision = evaluate_lhb_eligibility(
        trade_date="2026-06-26",
        ts_code="000004.SZ",
        lhb_reason="退市整理期",
        price_limit_state=main_board_state(pct_chg=-10.0),
        pump_risk=0.95,
        high_to_close_drawdown=0.12,
        institution_net_buy=None,
    )

    assert decision.eligibility_status == "hard_reject"
    assert decision.top5_eligible is False
    assert decision.backtest_entry_eligible is False
    assert decision.reason_codes[0] == "delisting_period"


@pytest.mark.parametrize("security_state", ["DELISTING_PERIOD", "退市整理", "listing_termination"])
def test_delisting_security_state_markers_are_hard_rejects(security_state):
    decision = evaluate_lhb_eligibility(
        trade_date="2026-06-26",
        ts_code="000004.SZ",
        lhb_reason="异常期间证券",
        security_state=security_state,
        price_limit_state=main_board_state(pct_chg=1.0),
        pump_risk=0.20,
        high_to_close_drawdown=0.01,
        institution_net_buy=1.0,
    )

    assert decision.eligibility_status == "hard_reject"
    assert decision.reason_codes == ("delisting_period",)


@pytest.mark.parametrize(
    ("pump", "status", "top5", "reason_or_warning"),
    [
        (0.7499, "eligible", True, ""),
        (0.75, "eligible", True, "high_elasticity_pump_risk"),
        (0.8999, "eligible", True, "high_elasticity_pump_risk"),
        (0.90, "hard_reject", False, "extreme_one_day_pump_risk"),
    ],
)
def test_pump_boundaries_are_shared(pump, status, top5, reason_or_warning):
    decision = evaluate_lhb_eligibility(
        trade_date="2026-07-14",
        ts_code="000001.SZ",
        lhb_reason="日涨幅偏离值达到7%的前5只证券",
        price_limit_state=main_board_state(pct_chg=1.0),
        pump_risk=pump,
        high_to_close_drawdown=0.01,
        institution_net_buy=1.0,
    )

    assert decision.eligibility_status == status
    assert decision.top5_eligible is top5
    observed = set(decision.reason_codes) | set(decision.warning_codes)
    if reason_or_warning:
        assert reason_or_warning in observed
    else:
        assert not observed


def test_near_limit_down_is_research_only():
    decision = evaluate_lhb_eligibility(
        trade_date="2026-07-14",
        ts_code="001399.SZ",
        lhb_reason="日跌幅偏离值达到7%的前5只证券",
        price_limit_state=main_board_state(pct_chg=-9.991),
        pump_risk=0.30,
        high_to_close_drawdown=0.02,
        institution_net_buy=None,
    )

    assert decision.eligibility_status == "risk_watch"
    assert decision.top5_eligible is False
    assert decision.backtest_entry_eligible is False
    assert "near_limit_down_followthrough_risk" in decision.reason_codes
    assert "institution_activity_unknown" in decision.warning_codes


def test_missing_pump_risk_fails_closed():
    decision = evaluate_lhb_eligibility(
        trade_date="2026-07-14",
        ts_code="000001.SZ",
        lhb_reason="日涨幅偏离值达到7%的前5只证券",
        price_limit_state=main_board_state(pct_chg=1.0),
        pump_risk=None,
        high_to_close_drawdown=0.01,
        institution_net_buy=1.0,
    )

    assert decision.eligibility_status == "risk_watch"
    assert decision.top5_eligible is False
    assert decision.backtest_entry_eligible is False
    assert decision.reason_codes == ("pump_risk_missing",)


def test_large_drawdown_is_warning_not_rejection():
    decision = evaluate_lhb_eligibility(
        trade_date="2026-07-14",
        ts_code="000001.SZ",
        lhb_reason="日涨幅偏离值达到7%的前5只证券",
        price_limit_state=main_board_state(pct_chg=1.0),
        pump_risk=0.30,
        high_to_close_drawdown=0.08,
        institution_net_buy=1.0,
    )

    assert decision.eligibility_status == "eligible"
    assert decision.top5_eligible is True
    assert "large_high_to_close_drawdown" in decision.warning_codes
