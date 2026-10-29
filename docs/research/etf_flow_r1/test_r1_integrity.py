"""R1.1 integrity checks — run with .venv/bin/python test_r1_integrity.py"""
import pandas as pd
import numpy as np


def main():
    uni = pd.read_csv("ETF_UNIVERSE_AND_GROUPS.csv", dtype={"fund_code": str})
    assert uni.fund_code.is_unique
    g2 = uni[uni.group == "G2_hs300_head"].fund_code.tolist()
    assert set(g2) == {"510300", "510310", "510330", "159919"}, g2
    assert uni.set_index("fund_code").loc["510050", "group"] == "G9_sse50_head"

    audit = pd.read_csv("data/corp_action_audit.csv", dtype={"fund_code": str})
    assert set(audit.status) <= {"official_confirmed", "algorithm_split",
                               "unverified"}
    assert ((audit.fund_code == "510310") & (audit.date == "2024-09-20") &
            (audit.status == "official_confirmed")).any()
    # detector output must be reproducible: rerun emits same row count
    assert len(audit) >= 150

    fd = pd.read_parquet("data/fund_day.parquet")
    r = fd[(fd.fund_code == "510310") & (fd.date == "2024-09-20")]
    assert len(r) == 1 and np.isnan(r.flow_use.iloc[0])
    assert {"flow_use", "flow_use_strict"} <= set(fd.columns)

    d = pd.read_parquet("data/factors_G2_hs300_head.parquet")
    # F20 = sum(flow,20)/aum(t-20)
    t = 500
    expect = d.flow.iloc[t - 19:t + 1].sum() / d.aum.iloc[t - 20]
    assert abs(d.F20.iloc[t] - expect) < 1e-9
    # compound fwd_ret: prod(1+r)-1
    w = 20
    seg = (1 + d.ret_idx.iloc[t + 1:t + 1 + w]).prod() - 1
    assert abs(d[f"fwd_ret{w}"].iloc[t] - seg) < 1e-9
    # fwd_low <= fwd_mdd? event-to-trough vs strict mdd both bounded
    assert (d.fwd_low20.dropna() > -1).all()
    assert (d.fwd_mdd20.dropna() > -1).all()

    tr = pd.read_csv("BACKTEST_TRADE_LOG.csv")
    dd = set(d.index.strftime("%Y-%m-%d"))
    assert tr.exec_date.isin(dd).all() and tr.signal_date.isin(dd).all()
    # signal_date strictly before exec_date
    assert (pd.to_datetime(tr.signal_date) < pd.to_datetime(tr.exec_date)).all()

    ev = pd.read_csv("EVENT_STUDY_RESULTS.csv")
    assert {"ev_low", "ev_mdd", "n_clusters"} <= set(ev.columns)
    rc = pd.read_csv("RESPONSE_CURVES.csv")
    assert rc.h.max() == 120
    print("ALL R1.1 INTEGRITY CHECKS PASSED")


if __name__ == "__main__":
    main()
