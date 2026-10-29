import pandas as pd
import glob

def test_all():
    l = pd.read_csv("WARNING_STATE_DAILY.csv")
    assert set(l.state) <= {"NORMAL", "WATCH", "ELEVATED",
                            "HIGH_PRESSURE", "RECOVERING"}
    wp, as_ = l.WP.dropna(), l["AS"].dropna()
    assert wp.between(0, 100).all() and as_.between(0, 100).all()
    assert wp.notna().mean() > 0.8   # min252 warmup only
    tr = pd.read_csv("WARNING_TRANSITIONS.csv")
    assert (tr["from"] != tr["to"]).all()
    assert tr.date.is_unique and tr.date.is_monotonic_increasing
    fr = pd.read_csv("FORWARD_RISK_BY_STATE.csv")
    assert (fr.n >= 3).all() and (fr.ev_mdd < 0).all()
    iv = pd.read_csv("INCREMENTAL_VALUE_VS_PRICE.csv")
    assert iv.precision.between(0, 1).all() and iv.recall.between(0, 1).all()
    assert len(glob.glob("0*.png")) == 9
    import os
    assert os.path.getsize("etf_risk_warning_poc.html") > 5_000_000
    print("ALL R2.1 CHECKS PASSED")

if __name__ == "__main__":
    test_all()
