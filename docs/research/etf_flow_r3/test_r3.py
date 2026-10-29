import pandas as pd

def test_all():
    c = pd.read_csv("FUND_FLOW_CYCLES.csv")
    assert (c.depth_max >= 0).all()
    assert c.cycle_id.notna().all()
    assert set(c.status) <= {"CLOSED", "OPEN"}
    assert (c[c.depth_max > 1.0].depth_flag == "DEPTH_GT_100").all()
    dd = pd.read_csv("FUND_FLOW_CYCLE_DAILY.csv")
    assert set(dd.fstate.dropna()) <= {"NEUTRAL", "WITHDRAWING",
        "WITHDRAWAL_DECELERATING", "FLOW_STABILIZING", "REACCUMULATING"}
    # every cycle row has matching daily rows
    for _, r in c.iterrows():
        sub = dd[(dd.group == r.group) & (dd.fcycle == r.cycle_id)]
        assert len(sub) >= r.dur_days - 1, r.cycle_id
    mon = pd.read_csv("CASE_A_2026_MONTHLY.csv")
    assert len(mon) == 10 and mon.cum_depth_pct.max() > 100
    fc = pd.read_csv("FAILED_CASES.csv")
    assert len(fc) >= 10
    import glob, os
    assert len(glob.glob("0*.png")) == 9
    assert os.path.getsize("etf_capital_cycle_r3.html") > 5_000_000
    print("ALL R3 CHECKS PASSED")

if __name__ == "__main__":
    test_all()
