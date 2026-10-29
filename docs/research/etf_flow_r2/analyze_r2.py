"""R2 pipeline: normalized-flow lag study + policy-state layer.

Imports R1.1 machinery from ../etf_flow_r1/analyze_r1.py (factors/clusters/
resp_curve/event_stats). Outputs per deliverable spec.
"""
import sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, "../etf_flow_r1")
from analyze_r1 import factors, clusters  # noqa: E402

R1D = "../etf_flow_r1/data"
FWIN = [20, 40, 60, 120]
LAG_BANDS = [(0, 5), (6, 10), (11, 20), (21, 40), (41, 60)]
OUT_T, IN_T, SH = -0.01, 0.01, 0.60


def load():
    fd = pd.read_parquet(f"{R1D}/fund_day.parquet")
    uni = pd.read_csv("../etf_flow_r1/ETF_UNIVERSE_AND_GROUPS.csv",
                      dtype={"fund_code": str})
    pe = pd.read_csv("POLICY_EVENTS.csv")
    groups = {}
    for p in __import__("pathlib").Path(R1D).glob("factors_*.parquet"):
        g = p.stem.replace("factors_", "")
        groups[g] = pd.read_parquet(p)
    return fd, uni, pe, groups


def augment(df):
    """Persistence + acceleration additions."""
    out = df.copy()
    sgn = np.sign(out.flow.fillna(0))
    pos_streak, neg_streak = [], []
    p = n = 0
    for v in sgn.values:
        p = p + 1 if v > 0 else 0
        n = n + 1 if v < 0 else 0
        pos_streak.append(p); neg_streak.append(n)
    out["pos_streak"], out["neg_streak"] = pos_streak, neg_streak
    out["F20_prev20"] = (out.flow.shift(20).rolling(20).sum()
                         / out.aum.shift(40))
    out["accel"] = out.F5 - out.F20_prev20
    out["cum_i20"] = out.i1.rolling(20).sum()          # legacy sum-of-ratios
    out["cum_i60"] = out.i1.rolling(60).sum()
    return out


def policy_flag(df, pe):
    """Days within 0..60 td after official events (action or document)."""
    ev = pe[pe.category.isin(["official_action", "official_document"])]
    dates = pd.to_datetime(ev.event_date)
    flag = np.zeros(len(df), bool)
    idx = df.index
    for d in dates:
        j = idx.searchsorted(d)
        flag[j:j + 60] = True
    return flag


def h1_price_to_flow(df, pname):
    rows = []
    r20 = df.ret_idx.rolling(20).sum()
    tert = pd.qcut(r20.dropna(), 3, labels=["dn", "mid", "up"])
    for lab, mask in [("dn", r20 <= r20.quantile(.33)),
                      ("up", r20 >= r20.quantile(.67))]:
        for lo, hi in LAG_BANDS:
            fband = df.i1.shift(-lo - 1).rolling(hi - lo).mean().shift(-(hi - lo - 1))
            rows.append({"group": pname, "ret_bucket": lab,
                         "lag": f"{lo}-{hi}",
                         "mean_fwd_i1_bp": round(
                             fband[mask].mean() * 1e4, 2),
                         "pol_mean_bp": round(
                             fband[mask & df.policy_on].mean() * 1e4, 2),
                         "nopol_mean_bp": round(
                             fband[mask & ~df.policy_on].mean() * 1e4, 2),
                         "n": int(mask.sum())})
    return rows


def ev_clusters(df, mask):
    pos = np.flatnonzero(mask.fillna(False).values)
    cls = clusters(list(pos))
    return [c[0] for c in cls], len(cls)


def h234_events(df, g):
    res = []
    defs = {
        "inflow": (df.F20 >= IN_T) & (df.inshare20 >= SH),
        "outflow": (df.F20 <= OUT_T) & (df.outshare20 >= SH),
        "up_out": (df.idx_ret20 > 0.02) & (df.F20 <= -0.005),
        "dn_in": (df.idx_ret20 < -0.02) & (df.F20 >= 0.005),
        "dn_out": (df.idx_ret20 < -0.02) & (df.F20 <= -0.005),
        "up_in": (df.idx_ret20 > 0.02) & (df.F20 >= 0.005),
        "hivol_out": (df.vol60 > df.vol60.median()) &
                     (df.F20 <= OUT_T) & (df.outshare20 >= SH),
        "lovol_out": (df.vol60 <= df.vol60.median()) &
                     (df.F20 <= OUT_T) & (df.outshare20 >= SH),
    }
    idx = df.index
    for kind, m in defs.items():
        ev, nc = ev_clusters(df, m)
        bad = np.zeros(len(df), bool)
        for p in ev:
            bad[max(0, p - 40):p + 60] = True
        pool = df[~bad & df.F20.notna()]
        for w in FWIN:
            evd = df.iloc[ev]
            er, el, em, evo = (evd[f"fwd_ret{w}"].dropna(), evd[f"fwd_low{w}"].dropna(),
                               evd[f"fwd_mdd{w}"].dropna(), evd[f"fwd_vol{w}"].dropna())
            if len(er) < 3:
                continue
            trough_days = []
            for p in ev:
                hi = min(len(df), p + 61)
                seg = df._px.values[p + 1:hi] / df._px.values[p]
                if len(seg) > 10:
                    trough_days.append(int(np.argmin(seg)) + 1)
            n = len(em)
            rng = np.random.default_rng(w)
            rep = [np.nanmean(em.values[rng.integers(0, n, n)]) for _ in range(300)]
            lo, hi2 = np.nanpercentile(rep, [5, 95])
            res.append({"group": g, "kind": kind, "window": w,
                        "n": n, "n_clusters": nc,
                        "ev_ret": round(er.mean(), 4),
                        "all_ret": round(pool[f"fwd_ret{w}"].mean(), 4),
                        "ev_low": round(el.mean(), 4),
                        "all_low": round(pool[f"fwd_low{w}"].mean(), 4),
                        "ev_mdd": round(em.mean(), 4),
                        "all_mdd": round(pool[f"fwd_mdd{w}"].mean(), 4),
                        "ev_vol": round(evo.mean(), 4),
                        "p_newlow": round((el < -0.02).mean(), 3),
                        "all_p_newlow": round((pool[f"fwd_low{w}"] < -0.02).mean(), 3),
                        "days_to_trough": round(np.mean(trough_days), 1) if trough_days else np.nan,
                        "ci_lo": round(lo, 4), "ci_hi": round(hi2, 4)})
    return res


def h5_policy_interaction(df, g):
    z = df.dropna(subset=["F20", "fwd_ret40"])
    on, off = z[z.policy_on], z[~z.policy_on]
    rng = np.random.default_rng(0)
    diffs = []
    for _ in range(300):
        so = on.iloc[rng.integers(0, len(on), len(on))] if len(on) else on
        sf = off.iloc[rng.integers(0, len(off), len(off))] if len(off) else off
        diffs.append(so.F20.corr(so.fwd_ret40) - sf.F20.corr(sf.fwd_ret40))
    lo, hi = np.nanpercentile(diffs, [5, 95])
    return {"group": g, "n_on": len(on), "n_off": len(off),
            "corr_on": round(on.F20.corr(on.fwd_ret40), 4),
            "corr_off": round(off.F20.corr(off.fwd_ret40), 4),
            "diff_ci_lo": round(lo, 4), "diff_ci_hi": round(hi, 4)}


def main():
    fd, uni, pe, groups = load()
    fdata = {}
    for g, df in groups.items():
        df.index = pd.to_datetime(df.index)
        df = augment(df)
        df["policy_on"] = policy_flag(df, pe)
        fdata[g] = df

    lag_rows, ev_rows, pol_rows, oos, fp = [], [], [], [], []
    for g, df in fdata.items():
        lag_rows += h1_price_to_flow(df, g)
        ev_rows += h234_events(df, g)
        pol_rows.append(h5_policy_interaction(df, g))
        z = df.dropna(subset=["F20"])
        for lab, sub in (("2020-2023", z[z.index < "2024-01-01"]),
                         ("2024-2025", z[(z.index >= "2024-01-01") &
                                       (z.index < "2026-01-01")]),
                         ("2026_touched", z[z.index >= "2026-01-01"])):
            if len(sub) > 60:
                oos.append({"group": g, "seg": lab, "n": len(sub),
                            "corr_F20_fwdret40": round(sub.F20.corr(sub.fwd_ret40), 4),
                            "corr_F20_fwdret120": round(sub.F20.corr(sub.fwd_ret120), 4),
                            "corr_idxret20_fwdF20": round(
                                sub.idx_ret20.corr(sub.F20.shift(-40)), 4)})
        # false positives: dn_in clusters failing to stabilize in 60d
        dn_in = (df.idx_ret20 < -0.02) & (df.F20 >= 0.005)
        ev, _ = ev_clusters(df, dn_in)
        for p in ev:
            r60, l60 = df[f"fwd_ret60"].iloc[p], df[f"fwd_low60"].iloc[p]
            if np.isnan(r60):
                continue
            fp.append({"group": g, "date": str(df.index[p])[:10],
                       "F20": round(df.F20.iloc[p], 4),
                       "fwd_ret60": round(r60, 4),
                       "fwd_low60": round(l60, 4),
                       "policy_on": bool(df.policy_on.iloc[p]),
                       "false_positive": bool((r60 <= 0) or (l60 <= -0.10))})

    pd.DataFrame(lag_rows).to_csv("LAG_RESPONSE_RESULTS.csv", index=False)
    pd.DataFrame(ev_rows).to_csv("FLOW_EVENT_RESULTS.csv", index=False)
    pd.DataFrame(pol_rows).to_csv("POLICY_REGIME_RESULTS.csv", index=False)
    pd.DataFrame(oos).to_csv("OOS_SEGMENTS.csv", index=False)
    pd.DataFrame(fp).to_csv("FALSE_POSITIVE_AUDIT.csv", index=False)
    for g, df in fdata.items():
        df.to_parquet(f"data/factors_{g}.parquet")
    print(json.dumps(pol_rows[:4], ensure_ascii=False))
    print("done")


if __name__ == "__main__":
    main()
