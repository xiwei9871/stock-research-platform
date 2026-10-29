"""R1 core analysis: factors F1-F5, H1/H2/H4 event studies, H3 tech scan,
backtest A/B/C. All thresholds follow RESEARCH_PLAN.md (pre-registered).

Outputs CSVs in this directory + data/factors.parquet for plotting.
"""
import json
import numpy as np
import pandas as pd

P = "../etf_flow_poc02/data"
FWIN = [5, 10, 20, 40, 60]
EVENT_DEDUP = 20
Z_BASE = 60
COST = 0.0005


def load_all():
    fd = pd.read_parquet("data/fund_day.parquet")
    gd = pd.read_parquet("data/group_daily_raw.parquet").reset_index()
    ir = pd.read_parquet("data/group_idx_ret.parquet").reset_index()
    ix = pd.read_csv(f"{P}/index_daily.csv", index_col="date")
    return fd, gd, ir, ix


def build_groups(fd, gd, ir, ix):
    """Return dict grp -> df(date, flow, aum, ret) incl. G1_all aggregate."""
    uni = pd.read_csv("ETF_UNIVERSE_AND_GROUPS.csv", dtype={"fund_code": str})
    gmap = uni.set_index("fund_code").group.to_dict()
    fd2 = fd[fd.fund_code.isin(gmap)]
    fd2 = fd2[fd2.fund_code.map(gmap) != "non_equity"].copy()
    fd2["grp"] = fd2.fund_code.map(gmap)
    fd2 = fd2.sort_values(["fund_code", "date"])
    fd2["mv_prev"] = fd2.groupby("fund_code").mv.shift(1)
    fd2["w"] = fd2.mv_prev * fd2.nav_ret
    agg = (fd2.groupby(["grp", "date"])
              .agg(flow=("flow_use", "sum"), aum=("mv", "sum"),
                   wnum=("w", "sum"), wden=("mv_prev", "sum"))
              .reset_index())
    agg["ret"] = agg.wnum / agg.wden
    groups = {}
    for g, sub in agg.groupby("grp"):
        groups[g] = sub.set_index("date").sort_index()
    # G1_all: all equity ETFs
    tot = agg.groupby("date")[["flow", "aum", "wnum", "wden"]].sum()
    tot["ret"] = tot.wnum / tot.wden
    groups["G1_all_equity"] = tot.sort_index()
    # raw-flow variant (corp hits included) for sensitivity
    fd3 = fd[fd.fund_code.isin(gmap)].copy()
    fd3["grp"] = fd3.fund_code.map(gmap)
    fd3 = fd3[fd3.grp != "non_equity"]
    raw = (fd3.groupby(["grp", "date"])
              .agg(flow_raw=("flow_yi", "sum")).reset_index())
    for g, sub in raw.groupby("grp"):
        groups.setdefault(g, pd.DataFrame())
        groups[g]["flow_raw"] = (sub.set_index("date").flow_raw
                                   .reindex(groups[g].index))
    groups["G1_all_equity"]["flow_raw"] = (
        raw.groupby("date").flow_raw.sum()
           .reindex(groups["G1_all_equity"].index))
    # attach market indices
    for g in groups:
        groups[g] = groups[g].join(ix[["hs300", "all_a"]], how="left")
        groups[g]["ret_idx"] = np.where(
            g in ("G2_hs300_head",),
            groups[g].hs300.pct_change(),
            np.where(g in ("G3_other_broad", "G1_all_equity"),
                     groups[g].all_a.pct_change(),
                     groups[g].ret))
        groups[g]["ret_mkt"] = groups[g].hs300.pct_change()
    return groups


def factors(df):
    out = df.copy()
    aum_lag = out.aum.shift(1)
    out["i1"] = out.flow / aum_lag
    for w in (5, 10, 20):
        out[f"i{w}"] = out.i1.rolling(w).sum()
    mu = out.i20.shift(1).rolling(Z_BASE).mean()
    sd = out.i20.shift(1).rolling(Z_BASE).std()
    out["z20"] = (out.i20 - mu) / sd
    med = out.i20.shift(1).rolling(Z_BASE).median()
    mad = (out.i20.shift(1).rolling(Z_BASE)
           .apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True))
    out["z20_mad"] = (out.i20 - med) / (1.4826 * mad)
    out["acc"] = out.i1.rolling(5).mean() - out.i1.rolling(20).mean()
    for w in FWIN:
        out[f"fwd_ret{w}"] = (out.ret_idx.shift(-1)
                              .rolling(w).sum().shift(-(w - 1)))
        # forward max drawdown within window
        px = (1 + out.ret_idx.fillna(0)).cumprod()
        out["_px"] = px
        lows = []
        arr = px.values
        for i in range(len(arr)):
            lo = arr[i + 1:i + 1 + w]
            lows.append((lo.min() / arr[i] - 1) if len(lo) else np.nan)
        out[f"fwd_mdd{w}"] = lows
    out["idx_ret20"] = out.ret_idx.rolling(20).sum()
    out["vol60"] = out.ret_idx.rolling(60).std()
    out["dd60"] = (out._px / out._px.rolling(60).max() - 1)
    return out


def dedupe(dates, min_gap=EVENT_DEDUP):
    dates = sorted(dates)
    kept, last = [], None
    for d in dates:
        if last is None or (d - last).days >= min_gap * 1.6:
            kept.append(d)
            last = d
    return kept


def events(df, col="z20", thr=-2.0):
    ev = df.index[df[col] <= thr] if thr < 0 else df.index[df[col] >= thr]
    return dedupe(list(pd.to_datetime(ev)))


def mblock_ci(stat_fn, n, B=400, block=40, seed=1):
    """CI via moving-block bootstrap; iid bootstrap when n < block."""
    rng = np.random.default_rng(seed)
    reps = []
    if n < block:
        for _ in range(B):
            reps.append(stat_fn(rng.integers(0, n, n)))
    else:
        for _ in range(B):
            idx = []
            while len(idx) < n:
                s = rng.integers(0, n - block + 1)
                idx.extend(range(s, s + block))
            reps.append(stat_fn(np.array(idx[:n])))
    reps = np.array(reps)
    return float(np.nanpercentile(reps, 5)), float(np.nanpercentile(reps, 95))


def event_stats(df, ev_dates, prefix):
    """Return list of result rows for event forward outcomes."""
    rows = []
    evset = set(ev_dates)
    dd = df.copy()
    dd.index = pd.to_datetime(dd.index)
    ev_mask = np.zeros(len(dd), bool)
    for d in ev_dates:
        j = dd.index.get_indexer([d])
        if j[0] >= 0:
            for k in range(max(0, j[0] - 20), min(len(dd), j[0] + 40)):
                ev_mask[k] = True
    ctrl_pool = dd[~ev_mask & dd.z20.notna()]
    # bucket matching: 20d ret tercile x vol60 tercile
    for w in FWIN:
        mdd_c = f"fwd_mdd{w}"
        sub = dd.loc[sorted(evset & set(dd.index))]
        ev_mdd = sub[mdd_c].dropna()
        if len(ev_mdd) < 3:
            continue
        ev_mdd.index = pd.to_datetime(ev_mdd.index)
        # matched controls
        m = []
        for d in ev_mdd.index:
            r, v, ddv = dd.loc[d, ["idx_ret20", "vol60", "dd60"]]
            cand = ctrl_pool[
                (ctrl_pool.idx_ret20.between(r - 0.03, r + 0.03)) &
                (ctrl_pool.vol60.between(v * 0.7, v * 1.3))]
            if len(cand):
                m.append(cand[mdd_c].mean())
        ctrl = pd.Series(m)
        all_mdd = ctrl_pool[mdd_c].dropna()
        ev_ret = dd.loc[ev_mdd.index, f"fwd_ret{w}"].dropna()
        ctrl_ret = ctrl_pool[f"fwd_ret{w}"].dropna()
        n = len(ev_mdd)
        lo, hi = mblock_ci(
            lambda idx_: float(np.nanmean(ev_mdd.values[idx_])),
            n, seed=w)
        rows.append({
            "group": prefix, "window": w, "n_events": n,
            "ev_mdd_mean": round(ev_mdd.mean(), 4),
            "ev_mdd_med": round(ev_mdd.median(), 4),
            "ev_ret_mean": round(ev_ret.mean(), 4),
            "ctrl_ret_mean": round(ctrl_ret.mean(), 4),
            "ctrl_mdd_mean": round(ctrl.mean(), 4) if len(ctrl) else np.nan,
            "all_mdd_mean": round(all_mdd.mean(), 4),
            "p_mdd_le5": round((ev_mdd <= -0.05).mean(), 3),
            "p_mdd_le10": round((ev_mdd <= -0.10).mean(), 3),
            "all_p_le5": round((all_mdd <= -0.05).mean(), 3),
            "all_p_le10": round((all_mdd <= -0.10).mean(), 3),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)})
    return rows


def reversal_events(df, lookback=10):
    """z20 <= -1 within past 10d, then z5 >= 0 first occurrence."""
    z20 = df.z20.values
    i5 = df.i5.values
    dates = list(pd.to_datetime(df.index))
    evs = []
    for t in range(Z_BASE + 20, len(dates)):
        if np.isnan(z20[t]) or np.isnan(i5[t]):
            continue
        win = z20[max(0, t - lookback):t]
        if i5[t] >= 0 and np.isfinite(win).any() and np.nanmin(win) <= -1:
            if not evs or (dates[t] - evs[-1]).days >= EVENT_DEDUP * 1.6:
                evs.append(dates[t])
    return evs


def bh_fdr(df, pcol, alpha=0.1):
    p = df[pcol].rank() if False else None
    return df


def backtest(df, sig_col="z20"):
    """A: hold; B: momentum+MA filter; C: B + flow override. T+1 exec."""
    px = (1 + df.ret_mkt.fillna(0)).cumprod().values
    ret = df.ret_mkt.fillna(0).values
    mom20 = df.ret_mkt.rolling(20).sum().values
    ma200 = df._px.rolling(200).mean().values
    z20 = df[sig_col].values
    i5 = df.i5.values
    n = len(df)
    posA = np.ones(n)
    posB = ((mom20 > 0) & (df._px.values > ma200)).astype(float)
    sig_exit = (z20 <= -2)
    posC = posB.copy()
    for t in range(1, n):
        if sig_exit[t - 1]:
            posC[t] = 0.0
        elif posB[t] == 1 and posC[t - 1] == 0:
            posC[t] = 1.0
    # T+1: shift positions by one day
    posB = np.roll(posB, 1); posB[0] = 0
    posC = np.roll(posC, 1); posC[0] = 0
    def stats(pos, name):
        sw = np.abs(np.diff(np.concatenate([[0], pos])))
        cost = sw * COST
        r = pos * ret - cost
        eq = np.cumprod(1 + r)
        mdd = (eq / np.maximum.accumulate(eq) - 1).min()
        yrs = n / 244
        ann = eq[-1] ** (1 / yrs) - 1
        vol = np.nanstd(r) * np.sqrt(244)
        dd = np.nanstd(np.minimum(r, 0)) * np.sqrt(244)
        calmar = ann / abs(mdd) if mdd else np.nan
        return {"strategy": name, "ann_ret": round(ann, 4),
                "vol": round(vol, 4), "max_dd": round(mdd, 4),
                "down_dev": round(dd, 4),
                "calmar": round(calmar, 3),
                "turnover": round(sw.sum(), 1),
                "n_trades": int((sw > 0).sum()),
                "pct_days_flat": round((pos == 0).mean(), 3),
                "final_eq": round(eq[-1], 3)}
    return [stats(posA, "A_hold_index"), stats(posB, "B_price_risk"),
            stats(posC, "C_price_plus_flow")]


def main():
    fd, gd, ir, ix = load_all()
    groups = build_groups(fd, gd, ir, ix)
    fdata = {g: factors(df) for g, df in groups.items()}

    lag_rows, ev_rows, rev_rows, div_rows, regime_rows = [], [], [], [], []
    for g, df in fdata.items():
        z = df.dropna(subset=["z20"])
        for w in FWIN:
            lag_rows.append({
                "group": g, "fwd_window": w,
                "corr_i20_fwdret": round(z.i20.corr(z[f"fwd_ret{w}"]), 4),
                "corr_i20_fwdmdd": round(z.i20.corr(z[f"fwd_mdd{w}"]), 4),
                "corr_idxret_fwdi20": round(
                    z.ret_idx.corr(z.i1.shift(-w).rolling(w).sum()
                                   .shift(-(w - 1))), 4),
                "n": len(z)})
        # H1 outflow events
        for thr in (-2.0, -2.5):
            evs = events(df, "z20", thr)
            for r in event_stats(df, evs, g):
                r["thr"] = thr
                r["kind"] = "H1_outflow"
                ev_rows.append(r)
        # H2 reversal
        rev = reversal_events(df)
        for r in event_stats(df, rev, g):
            r["thr"] = "rev_z5>=0"
            r["kind"] = "H2_reversal"
            rev_rows.append(r)
        # H4 divergence
        for lab, msk in (("A_up_out", (df.idx_ret20 > 0.02) & (df.z20 < -1)),
                         ("B_down_in", (df.idx_ret20 < -0.02) & (df.z20 > 1))):
            evs = dedupe(list(pd.to_datetime(df.index[msk.fillna(False)])))
            for r in event_stats(df, evs, g):
                r["thr"] = lab
                r["kind"] = f"H4_{lab}"
                div_rows.append(r)
        # regime: split by vol60 median & idx_ret20 sign
        zz = df.dropna(subset=["z20"])
        hi_v = zz.vol60 > zz.vol60.median()
        for lab, mm in (("hi_vol", hi_v), ("lo_vol", ~hi_v),
                        ("up20", zz.idx_ret20 > 0), ("dn20", zz.idx_ret20 <= 0)):
            sub = zz[mm]
            regime_rows.append({
                "group": g, "regime": lab, "n": len(sub),
                "corr_i20_fwdret20": round(sub.i20.corr(sub.fwd_ret20), 4),
                "corr_i20_fwdmdd20": round(sub.i20.corr(sub.fwd_mdd20), 4)})

    pd.DataFrame(lag_rows).to_csv("FLOW_RETURN_LAG_ANALYSIS.csv", index=False)
    all_ev = pd.DataFrame(ev_rows + rev_rows + div_rows)
    all_ev.to_csv("EVENT_STUDY_RESULTS.csv", index=False)
    pd.DataFrame(regime_rows).to_csv("REGIME_COMPARISON.csv", index=False)

    # sensitivity: raw vs corrected for G2 & G1_all
    sens = []
    for g in ("G2_hs300_head", "G1_all_equity"):
        df = fdata[g].copy()
        df["flow"] = df.flow_raw.fillna(df.flow)
        df2 = factors(df)
        evs = events(df2, "z20", -2.0)
        sens += [{"group": g, "variant": "raw",
                  "n_events": len(evs),
                  "dates": ";".join(str(x)[:10] for x in evs)}]
        evs2 = events(fdata[g], "z20", -2.0)
        sens += [{"group": g, "variant": "corrected",
                  "n_events": len(evs2),
                  "dates": ";".join(str(x)[:10] for x in evs2)}]
    pd.DataFrame(sens).to_csv("SENSITIVITY_CORP_ACTION.csv", index=False)

    # backtest on G2 signal (hs300 underlying)
    bt = backtest(fdata["G2_hs300_head"])
    pd.DataFrame(bt).to_csv("RISK_MANAGEMENT_BACKTEST.csv", index=False)
    print(json.dumps(bt, ensure_ascii=False))

    # OOS split metrics for the z20-outflow->mdd link
    oos = []
    for g, df in fdata.items():
        z = df.dropna(subset=["z20"])
        for lab, sub in (("train_2020_2023", z[z.index < "2024-01-01"]),
                         ("oos_2024_2026", z[z.index >= "2024-01-01"])):
            if len(sub) < 100:
                continue
            oos.append({"group": g, "segment": lab, "n": len(sub),
                        "corr_i20_fwdret20": round(
                            sub.i20.corr(sub.fwd_ret20), 4),
                        "corr_i20_fwdmdd20": round(
                            sub.i20.corr(sub.fwd_mdd20), 4),
                        "corr_i20_fwdret40": round(
                            sub.i20.corr(sub.fwd_ret40), 4)})
    pd.DataFrame(oos).to_csv("OOS_VALIDATION.csv", index=False)

    # persist factor frame for plots + case studies
    for g, df in fdata.items():
        df.to_parquet(f"data/factors_{g}.parquet")
    print("done")


if __name__ == "__main__":
    main()
