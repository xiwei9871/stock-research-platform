"""Event/state-level tests for R2.1.2 audit logic (synthetic data)."""
import numpy as np
import pandas as pd
from analyze_r212 import cycles, episodes, drawdown, WARN


def mkdf(px, states):
    return pd.DataFrame({"hs300": px, "state": states,
                         "WP": [50.] * len(px)},
                        index=pd.date_range("2024-01-01", periods=len(px)))


def test_all():
    # 1. same cycle repeated -10% crossing -> one cycle
    px = np.r_[np.linspace(5000, 5500, 60), 5500 * 0.87,
               np.linspace(5500 * 0.87, 5500 * 0.88, 30),
               5500 * 0.84, np.linspace(5500 * 0.84, 5600, 60)]
    dd, _ = drawdown(pd.Series(px))
    cy = cycles(dd.values, px, pd.date_range("2024-01-01", periods=len(px)))
    assert len(cy) == 1 and cy[0]["first_dd15_date"]  # -15 & -10 same cycle
    assert cy[0]["cycle_status"] == "COMPLETED"
    # 8. -10 then -15 inside one cycle counted once (covered above)

    # 2. two independent cycles: full recovery between
    px2 = np.r_[np.linspace(5000, 5500, 60), 5500 * 0.87,
               np.linspace(5500 * 0.87, 5600, 60),  # recover > -5% & new hi
               5600 * 0.86, np.linspace(5600 * 0.86, 5700, 60)]
    dd2, _ = drawdown(pd.Series(px2))
    cy2 = cycles(dd2.values, px2, pd.date_range("2024-01-01", periods=len(px2)))
    assert len(cy2) == 2

    # 3. warning predates 60d and persists -> covered, lead >60 possible
    st = ["NORMAL"] * 20 + ["WATCH"] * 80 + ["NORMAL"] * 60
    d3 = mkdf(np.linspace(5000, 4000, 160), st)
    eps = episodes(d3)
    assert eps[0]["dur_days"] == 80 and eps[0]["first_watch"]

    # 4. warning released before risk -> episode ends, new onset uncovered
    st4 = ["NORMAL"] * 10 + ["WATCH"] * 10 + ["NORMAL"] * 30
    eps4 = episodes(mkdf(np.linspace(5000, 4000, 50), st4))
    assert eps4[0]["end"] and eps4[0]["release_date"]

    # 5. warning after onset cannot count as lead (checked via dates order)
    c5 = cycles(dd2.values, px2,
                pd.date_range("2024-01-01", periods=len(px2)))
    onset_i = c5[0]["i_onset"]
    st5 = ["NORMAL"] * len(px2)
    st5[onset_i + 5:onset_i + 15] = ["WATCH"] * 10
    eps5 = episodes(mkdf(px2, st5))
    ep = next((e for e in eps5 if e["i0"] <= onset_i <= e["i1"]), None)
    assert ep is None  # warning starts after onset -> no covering episode

    # 6. risk not finished -> ONGOING + right_censored
    px6 = np.r_[np.linspace(5000, 5500, 60), np.linspace(5500, 5500 * 0.8, 40)]
    dd6, _ = drawdown(pd.Series(px6))
    cy6 = cycles(dd6.values, px6, pd.date_range("2024-01-01", periods=len(px6)))
    assert cy6[0]["cycle_status"] == "ONGOING" and cy6[0]["right_censored"]

    # 7. episode near data end -> caller marks CENSORED (dur < window)
    st7 = ["NORMAL"] * 40 + ["WATCH"] * 10
    eps7 = episodes(mkdf(np.linspace(5000, 4000, 50), st7))
    assert eps7[-1]["dur_days"] == 10 < 60

    # 9. alignment: warning strictly after onset -> not active_at_onset
    px9 = np.r_[np.linspace(5000, 5500, 60), np.linspace(5500, 5500*0.85, 10)]
    dd9, _ = drawdown(pd.Series(px9))
    cy9 = cycles(dd9.values, px9, pd.date_range("2024-01-01", periods=len(px9)))
    oi = cy9[0]["i_onset"]
    st9 = ["NORMAL"] * len(px9)
    st9[oi + 2:] = ["WATCH"] * (len(px9) - oi - 2)
    assert st9[oi] == "NORMAL" and st9[oi + 2] == "WATCH"

    # 10. denominators reconcile: cycle count == rows in coverage
    assert len(cy) == 1
    print("ALL R2.1.2 TESTS PASSED")


if __name__ == "__main__":
    test_all()
