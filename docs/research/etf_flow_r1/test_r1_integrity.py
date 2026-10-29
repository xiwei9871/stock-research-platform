"""R1 integrity checks — run with .venv/bin/python test_r1_integrity.py"""
import pandas as pd
import numpy as np


def main():
    uni = pd.read_csv("ETF_UNIVERSE_AND_GROUPS.csv", dtype={"fund_code": str})
    # groups mutually exclusive
    assert uni.fund_code.is_unique, "fund_code duplicated in universe"
    assert set(uni.group) <= {"G1_sector_other", "G2_hs300_head",
                              "G3_other_broad", "G4k_star", "G5_semiconductor",
                              "G6_ai_compute", "G7_robot", "G8_softinfo",
                              "non_equity"}

    fd = pd.read_parquet("data/fund_day.parquet")
    # 510310 merge day must be masked out of analysis flow
    r = fd[(fd.fund_code == "510310") & (fd.date == "2024-09-20")]
    assert len(r) == 1 and np.isnan(r.flow_use.iloc[0]), \
        "510310 2024-09-20 not masked"

    audit = pd.read_csv("data/corp_action_audit.csv", dtype={"fund_code": str})
    assert len(audit) >= 148 - 5

    g2 = pd.read_parquet("data/factors_G2_hs300_head.parquet")
    # z-score baseline uses only past data: z20 at t must be computable from
    # i20 values strictly before t — verify no NaN leak in first 60 obs and
    # that z20 is NaN until baseline exists
    assert g2.z20.iloc[:61].isna().all()
    # intensity denominator is lagged AUM
    aum = g2.aum
    assert np.allclose(g2.i1.dropna().iloc[100:110],
                       (g2.flow / aum.shift(1)).dropna().iloc[100:110])
    # forward mdd bounded within sane range (can be >0 if never dips below T)
    v = g2.fwd_mdd20.dropna()
    assert (v > -1).all() and (v < 0.5).all()

    ev = pd.read_csv("EVENT_STUDY_RESULTS.csv")
    assert {"group", "window", "n_events", "ev_mdd_mean"} <= set(ev.columns)
    bt = pd.read_csv("RISK_MANAGEMENT_BACKTEST.csv")
    assert set(bt.strategy) == {"A_hold_index", "B_price_risk",
                                "C_price_plus_flow"}
    print("ALL INTEGRITY CHECKS PASSED")


if __name__ == "__main__":
    main()
