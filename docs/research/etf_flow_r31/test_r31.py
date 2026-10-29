"""R3.1 PIT engine tests."""
import pandas as pd, numpy as np, sys
sys.path.insert(0, ".")
from analyze_r31 import engine, first_touch, replay_test

def small():
    idx = pd.date_range("2020-01-01", periods=60, freq="B")
    return pd.DataFrame({
        "flow": [-10]*60, "aum": [1000]*60,
        "outshare20": [0.7]*60, "F20": [-0.1]*60,
        "idx_level": np.linspace(100,90,60),
    }, index=idx)

def test_detection_after_10_days():
    d, c = engine(small())
    assert c[0]["open_i"] >= 9, "cycle must be confirmed, not backdated"
    assert d.pcyc.iloc[0] == "", "pre-detection days must not carry cycle id"
    assert d.pdepth.iloc[c[0]["open_i"]] > 0

def test_replay_consistency():
    d = pd.read_parquet("../etf_flow_r21/data/factors_G2_hs300_head.parquet")
    d.index = pd.to_datetime(d.index)
    assert replay_test(d)

def test_first_touch_pit():
    d = pd.read_parquet("../etf_flow_r21/data/factors_G2_hs300_head.parquet")
    d.index = pd.to_datetime(d.index)
    d2, cycs = engine(d)
    ev = pd.DataFrame(first_touch(d2, cycs))
    for _, r in ev.iterrows():
        c = [c for c in cycs if c["id"] == r.cycle_id][0]
        assert pd.Timestamp(r.date) >= d.index[c["open_i"]], \
            "event before detection = leakage"
        assert r.depth >= r.threshold - 0.01
    assert ev.groupby(["cycle_id","threshold"]).size().max() == 1, \
        "duplicate threshold events"

def test_velocity_units():
    d, _ = engine(small())
    # vel5 = mean daily flow / aum -> 10/1000 = 1% per day
    assert abs(d.vel5.iloc[-1] - (-1.0)) < 1e-6, "vel5 must be %AUM/day"

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print(f"{k} PASS")
    print("ALL R3.1 CHECKS PASSED")
