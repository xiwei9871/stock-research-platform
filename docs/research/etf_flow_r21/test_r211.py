"""State-machine unit tests: synthetic WP/AS sequences vs spec."""
import numpy as np
import pandas as pd
from analyze_r211 import state_machine


def mk(wp, as_=None, o40=None, n_px=300):
    n = len(wp)
    d = pd.DataFrame({"WP": wp, "AS": as_ if as_ is not None else [0.0] * n,
                      "outshare40": o40 if o40 is not None else [0.0] * n,
                      "ret_idx": [0.0] * n,
                      "hs300": np.linspace(4000, 5000, n),
                      "F20": [0.0] * n},
                     index=pd.date_range("2024-01-01", periods=n))
    return state_machine(d)


def test_rules():
    # NORMAL->WATCH needs wp>=70 for exactly 5d
    d = mk([0] * 5 + [72] * 4 + [10] * 20 + [72] * 5 + [10] * 10)
    assert d.state.iloc[8] == "NORMAL"          # 4 days not enough
    assert d.state.iloc[32] == "NORMAL"         # 4th of second run
    assert d.state.iloc[33] == "WATCH"          # 5th consecutive day
    # WATCH->ELEVATED wp>=80 5d; 4d gap below 70 resets e counter
    # (4d <60 keeps WATCH: RECOVERING needs 5d)
    d = mk([0] * 5 + [75] * 5 + [82] * 4 + [10] * 4 + [82] * 5 + [10] * 10)
    assert d.state.iloc[13] == "WATCH"          # 4d at 82 insufficient
    assert d.state.iloc[17] == "WATCH"          # gap: r counter only 4
    assert d.state.iloc[21] == "WATCH"          # 4th of second 82-run
    assert d.state.iloc[22] == "ELEVATED"
    # ELEVATED->HIGH needs wp>=85 for 10d (spec), not 5
    d = mk([0] * 5 + [75] * 5 + [82] * 5 + [90] * 9 + [10] * 4
           + [90] * 10 + [10] * 10)
    assert d.state.iloc[23] == "ELEVATED"       # 9d at 90 insufficient
    assert d.state.iloc[36] == "ELEVATED"       # 9th of second run
    assert d.state.iloc[37] == "HIGH_PRESSURE"  # 10th day per spec
    # ELEVATED->HIGH alt path: wp>=75 & outshare40>=0.6 held 10d
    d = mk([0] * 5 + [75] * 5 + [82] * 5 + [76] * 10 + [10] * 10,
           o40=[0] * 15 + [0.7] * 10 + [0] * 10)
    assert d.state.iloc[24] == "HIGH_PRESSURE"
    # HIGH->RECOVERING wp<60 for 5d
    d = mk([0] * 5 + [75] * 5 + [82] * 5 + [90] * 10 + [55] * 4 + [10] * 20)
    assert d.state.iloc[28] == "HIGH_PRESSURE"
    assert d.state.iloc[29] == "RECOVERING"
    # RECOVERING->NORMAL wp<60 10d
    d = mk([0] * 5 + [75] * 5 + [82] * 5 + [90] * 10 + [55] * 5 + [55] * 15)
    assert d.state.iloc[34] == "RECOVERING"
    assert d.state.iloc[39] == "NORMAL"
    # RECOVERING->WATCH re-entry wp>=70 5d
    d = mk([0] * 5 + [75] * 5 + [82] * 5 + [90] * 10 + [55] * 5 + [72] * 5
           + [10] * 10)
    assert d.state.iloc[34] == "WATCH"
    # counter isolation: 4d wp>=70 then drop; AS only 1d -> no transition
    d = mk([0] * 5 + [72] * 4 + [65] * 6, as_=[0] * 9 + [70] * 1 + [0] * 5)
    assert d.state.iloc[8] == "NORMAL"   # 4d at 72, w counter=4
    assert d.state.iloc[9] == "NORMAL"   # wp=65 resets w; as=70 only 1d
    assert d.state.iloc[14] == "NORMAL"  # no spurious jump from shared counter
    print("STATE MACHINE UNIT TESTS PASSED")


if __name__ == "__main__":
    test_rules()
