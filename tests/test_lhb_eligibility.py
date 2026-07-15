import pytest

from stock_research.lhb_eligibility import resolve_price_limit_state


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
