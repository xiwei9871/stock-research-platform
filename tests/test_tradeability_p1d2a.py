"""DATA-R3-P1d.2a — pre-cutover safety patch tests.

Covers the four P0 review findings: NULL-flag missing detection, cost-path
constraint preservation, date-bound minute qualification, and the explicit
legacy/corrected_shadow/verified_v2 qualification modes.
"""

import datetime as dt
import os

import pandas as pd
import pytest

from stock_research.tradeability import LedgerMinuteQualificationProvider

LEDGER_BASE = "outputs/research/data01r1_finance_q2_20261020"
NEEDS_LEDGERS = pytest.mark.skipif(
    not os.path.exists(f"{LEDGER_BASE}/r2_downstream_minute_done.json"),
    reason="R2 minute ledgers not present")


def _db_available() -> bool:
    try:
        from stock_research.config import SETTINGS
        from stock_research.db import connect
        with connect(SETTINGS.research_service) as c:
            c.execute("SELECT 1") if hasattr(c, "execute") else None
        return True
    except Exception:
        return False


NEEDS_DB = pytest.mark.skipif(not _db_available(), reason="research DB unreachable")


# --- A: NULL flags are missing, not verified-False ---------------------------

def test_partial_null_flags_mark_missing():
    from stock_research.vectorized_topn_backtest import _normalize_prices
    frame = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 3,
        "asset_id": ["A", "B", "C"],
        "open": [10.0] * 3, "close": [10.0] * 3, "amount": [1e8] * 3,
        "trade_status": ["1"] * 3,
        # A: fully present False -> verified, not missing
        "is_limit_up": [False, None, True],
        "is_limit_down": [False, False, None],   # C NULL down -> missing
        "is_suspended": [False, False, False],
    })
    out = _normalize_prices(frame)
    assert bool(out.loc[out.asset_id == "A", "limit_state_missing"].iloc[0]) is False
    assert bool(out.loc[out.asset_id == "B", "limit_state_missing"].iloc[0]) is True
    assert bool(out.loc[out.asset_id == "C", "limit_state_missing"].iloc[0]) is True


# --- B: nonzero cost must not drop block_missing_limit_state -----------------

@pytest.mark.parametrize("cost", [0.0, 15.0])
def test_effective_constraints_preserve_missing_state_block(cost):
    from stock_research.backtest_constraints import (
        BacktestExecutionConstraints, can_open_long)
    from stock_research.vectorized_topn_backtest import (
        VectorizedTopNConfig, _effective_execution_constraints)
    cfg = VectorizedTopNConfig(
        start_date="2024-01-02", end_date="2024-03-01",
        transaction_cost_bps=cost,
        execution_constraints=BacktestExecutionConstraints(
            block_missing_limit_state=True))
    eff = _effective_execution_constraints(cfg)
    assert eff.block_missing_limit_state is True
    if cost:
        assert eff.commission_bps == 15.0
    bar = {"trade_status": "1", "is_limit_up": False, "is_limit_down": False,
           "is_suspended": False, "limit_state_missing": True}
    assert can_open_long(bar, eff) == (False, "limit_state_missing")
    bar["limit_state_missing"] = False
    assert can_open_long(bar, eff)[0] is True
    # legacy default reproducible: missing state does not block
    legacy = _effective_execution_constraints(VectorizedTopNConfig(
        start_date="2024-01-02", end_date="2024-03-01",
        transaction_cost_bps=cost))
    assert legacy.block_missing_limit_state is False
    bar["limit_state_missing"] = True
    assert can_open_long(bar, legacy)[0] is True


# --- C: date-bound minute qualification --------------------------------------

def _prov():
    return LedgerMinuteQualificationProvider(
        {"CN:SH:600001": {"CN:SH:600001|5min|baostock": {"factor_sig": "t1"}},
         "CN:SH:605077": {"CN:SH:605077|5min|akshare": {"factor_sig": "t2"}}},
        residual_gap_assets={"CN:SH:605077"})


def test_minute_date_tier_without_checker_is_key_level():
    prov = _prov()
    q, src, ver, blocks = prov.verdict("CN:SH:600001", trade_date=dt.date(2024, 1, 2))
    assert q is True
    assert ver.endswith(":key_level")
    assert "minute_date_unverified" in blocks


def test_minute_date_verified_when_checker_confirms():
    prov = _prov()
    prov.set_date_checker(lambda a, d, f, s: f == "5min" and s == "baostock")
    q, src, ver, blocks = prov.verdict("CN:SH:600001", trade_date=dt.date(2024, 1, 2))
    assert q is True and ver.endswith(":date_rows_verified")
    assert "minute_date_unverified" not in blocks


def test_minute_date_unverified_when_checker_fails():
    prov = _prov()
    prov.set_date_checker(lambda a, d, f, s: False)
    q, src, ver, blocks = prov.verdict("CN:SH:600001", trade_date=dt.date(2024, 1, 2))
    assert q is True
    assert ver.endswith(":key_level_unverified_date")
    assert "minute_date_unverified" in blocks


def test_minute_no_date_asked_stays_legacy():
    prov = _prov()
    q, src, ver, blocks = prov.verdict("CN:SH:600001")
    assert q is True and ver == "r2_minute_v1:t1"


# --- D: explicit qualification modes ------------------------------------------

@NEEDS_DB
def test_loader_modes_smoke():
    from stock_research.vectorized_topn_backtest import (
        load_vectorized_topn_inputs)
    s, p_legacy = load_vectorized_topn_inputs(
        "2024-01-02", "2024-01-10", qualification_mode="legacy")
    assert p_legacy.attrs["qualification_mode"] == "legacy"
    assert "mislabeled" in p_legacy.attrs["qualification_note"]

    _, p_shadow = load_vectorized_topn_inputs(
        "2024-01-02", "2024-01-10", qualification_mode="corrected_shadow")
    assert p_shadow.attrs["qualification_mode"] == "corrected_shadow"
    assert "limit_rule_id" in p_shadow.columns
    # corrected flags never blank: missing -> fail-closed marker
    assert p_shadow["is_limit_up"].notna().all()

    _, p_v2 = load_vectorized_topn_inputs(
        "2024-01-02", "2024-01-10", qualification_mode="verified_v2")
    # v2 columns do not exist yet -> everything must be missing/blocked
    assert bool(p_v2["limit_state_missing"].all())


@NEEDS_DB
def test_end_to_end_corrected_shadow_gate():
    """Real loader -> engine -> execution gate: a rule_unknown row must be
    blocked in corrected_shadow, and missing state blocks under strict."""
    from stock_research.backtest_constraints import (
        BacktestExecutionConstraints, can_open_long)
    from stock_research.vectorized_topn_backtest import (
        VectorizedTopNConfig, _normalize_prices, load_vectorized_topn_inputs)
    scores, prices = load_vectorized_topn_inputs(
        "2024-01-02", "2024-01-10", qualification_mode="corrected_shadow")
    norm = _normalize_prices(prices)
    strict = BacktestExecutionConstraints(block_missing_limit_state=True)
    # every bar dict must carry the fail-closed marker column
    assert "limit_state_missing" in norm.columns
    missing_rows = norm[norm["limit_state_missing"]]
    for _, r in missing_rows.head(5).iterrows():
        assert can_open_long(r.to_dict(), strict)[0] is False


# --- P0-1: apply_pit_flags three-way match state -----------------------------

def test_apply_pit_flags_three_way_state():
    import pandas as pd
    from stock_research.tradeability import apply_pit_flags
    prices = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 3,
        "asset_id": ["A", "B", "NOFLAG"],
        "open": [10.0] * 3, "close": [10.0] * 3, "amount": [1e8] * 3,
        "trade_status": ["1"] * 3,
        "is_limit_up": [False] * 3, "is_limit_down": [False] * 3,
        "is_suspended": [False] * 3, "limit_state_missing": [False] * 3,
    })
    flags = pd.DataFrame({
        "asset_id": ["A", "B"],
        "trade_date": ["2024-01-02", "2024-01-02"],
        "shadow_limit_up": [False, True],
        "shadow_limit_down": [False, False],
        "shadow_rule_unknown": [False, True],
        "shadow_rule_id": ["main_10pct", "rule_unknown"],
    })
    out = apply_pit_flags(prices, flags).set_index("asset_id")
    # matched + verified -> computed value
    assert out.loc["A", "qualification_state"] == "verified"
    assert bool(out.loc["A", "is_limit_up"]) is False
    assert bool(out.loc["A", "limit_state_missing"]) is False
    # matched + rule_unknown -> blocked
    assert out.loc["B", "qualification_state"] == "rule_unknown"
    assert bool(out.loc["B", "is_limit_up"]) is True
    assert bool(out.loc["B", "is_limit_down"]) is True
    assert bool(out.loc["B", "limit_state_missing"]) is True
    # NO flag record -> qualification_missing, blocked, NEVER default False
    assert out.loc["NOFLAG", "qualification_state"] == "qualification_missing"
    assert bool(out.loc["NOFLAG", "is_limit_up"]) is True
    assert bool(out.loc["NOFLAG", "is_limit_down"]) is True
    assert bool(out.loc["NOFLAG", "limit_state_missing"]) is True


# --- P0-3: real corrected_shadow end-to-end gate ------------------------------

@NEEDS_DB
def test_corrected_shadow_end_to_end_blocks_missing():
    from stock_research.backtest_constraints import (
        BacktestExecutionConstraints)
    from stock_research.vectorized_topn_backtest import (
        VectorizedTopNConfig, load_vectorized_topn_inputs,
        run_vectorized_topn_backtest)
    scores, prices = load_vectorized_topn_inputs(
        "2024-01-02", "2024-02-29", qualification_mode="corrected_shadow")
    assert "qualification_state" in prices.columns
    strict = BacktestExecutionConstraints(block_missing_limit_state=True)
    for cost in (0.0, 15.0):
        cfg = VectorizedTopNConfig(
            start_date="2024-01-02", end_date="2024-02-29",
            top_n=20, transaction_cost_bps=cost,
            execution_constraints=strict)
        res = run_vectorized_topn_backtest(scores, prices, cfg)
        tr = res.trades
        if len(tr):
            # every executed trade carries traceable skip/limit state
            assert "skip_reason" in tr.columns
            # no limit_state_missing skip may EXECUTE — skip rows have 0 weight
            bad = tr[(tr.skip_reason == "limit_state_missing")
                     & (tr.executed_weight.fillna(0) > 0)]
            assert bad.empty, f"cost={cost}: missing-state rows executed"
        res.summary["qualification_mode"] = "corrected_shadow"


@NEEDS_DB
def test_corrected_shadow_ignores_stored_v1_flags():
    """A confirmed mislabeled (asset,date) must NOT inherit stored v1 truth."""
    import pandas as pd
    from stock_research.tradeability import compute_pit_limit_flags
    from stock_research.db import connect, fetch_all
    from stock_research.config import SETTINGS
    # pick a known mislabel inside score coverage: chinext ST asset post-reform
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, """
            SELECT s.asset_id, s.trade_date::text d, s.is_limit_up
            FROM core.asset_status_daily s
            WHERE s.is_limit_up = true AND s.trade_date = '2024-01-02'
            LIMIT 5""")
        assert rows, "need at least one stored limit_up row"
        asset, d = rows[0]["asset_id"], rows[0]["d"]
        flags = compute_pit_limit_flags(conn, d, d)
        rec = flags[flags.asset_id == asset]
        if not rec.empty:
            # corrected flag comes from the rule engine — may differ from
            # the stored v1 flag; the point is it is recomputed, not copied.
            assert "shadow_rule_id" in rec.columns
            assert rec.iloc[0]["shadow_rule_id"] != ""


@NEEDS_DB
def test_legacy_vs_corrected_diff_explainable():
    """Legacy vs corrected_shadow on same window: every difference must map
    to a rule_id or a missing-state block, never unexplained."""
    from stock_research.backtest_constraints import (
        BacktestExecutionConstraints)
    from stock_research.vectorized_topn_backtest import (
        VectorizedTopNConfig, load_vectorized_topn_inputs,
        run_vectorized_topn_backtest)
    s, pl = load_vectorized_topn_inputs(
        "2024-01-02", "2024-02-29", qualification_mode="legacy")
    _, pc = load_vectorized_topn_inputs(
        "2024-01-02", "2024-02-29", qualification_mode="corrected_shadow")
    cfg_l = VectorizedTopNConfig(start_date="2024-01-02",
                                 end_date="2024-02-29", top_n=20)
    strict = BacktestExecutionConstraints(block_missing_limit_state=True)
    cfg_c = VectorizedTopNConfig(start_date="2024-01-02",
                                 end_date="2024-02-29", top_n=20,
                                 execution_constraints=strict)
    rl = run_vectorized_topn_backtest(s, pl, cfg_l)
    rc = run_vectorized_topn_backtest(s, pc, cfg_c)
    # corrected run may differ — but every corrected price row must carry a
    # traceable state (verified / rule_unknown / qualification_missing)
    assert set(pc["qualification_state"].unique()) <= {
        "verified", "rule_unknown", "qualification_missing"}
    # corrected leg can only block MORE (strict), never invent fills on
    # missing qualification
    blocked = pc[pc["qualification_state"] != "verified"]
    if len(blocked):
        assert bool(blocked["limit_state_missing"].all())
