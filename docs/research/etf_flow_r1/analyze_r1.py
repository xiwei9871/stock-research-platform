"""R1.1 analysis pipeline — methodology-audited revision.

Changes vs R1:
- Primary factor F_w = rolling sum of flows over window / AUM at window start
  (window flow intensity), daily i1 kept; i20 (sum of daily ratios) secondary.
- Forward returns are COMPOUND (log1p), not arithmetic sums.
- Forward risk outputs BOTH event-to-trough decline (fwd_low) and strict
  peak-to-trough max drawdown (fwd_mdd) within window.
- Forward windows extended to 120 trading days; response curves 0..120d.
- Events deduplicated into CLUSTERS (>=20 trading-day gap); effective n is
  reported as n_clusters.
- Backtest single-lag convention: signals computed on day-t data act on the
  day-(t+1) return via one np.roll; costs deducted on the execution day.
  Daily trade log exported; alignment assertions enforced.
- Corp-action candidates layered: only official_confirmed + algorithm_split
  masked in flow_use; 'unverified' additionally masked in flow_use_strict.
- Real sector indices used where coverage allows (sse50, star50); tech
  subthemes use MV-weighted proxy (csindex series end 2024-06 -> marked proxy).
"""
import json
import numpy as np
import pandas as pd

P = "../etf_flow_poc02/data"
FWIN = [5, 10, 20, 40, 60, 120]
CLUSTER_GAP = 20           # trading days
Z_BASE = 60
COST = 0.0005
OUT_THR, IN_THR = -0.01, 0.01     # F20 window-intensity thresholds
OUTSHARE = 0.60                    # share of net-outflow days in window
INFLECT_THR = 0.015                # F20 improvement >= +1.5pp

REAL_IDX = {"G9_sse50_head": "sse50", "G4k_star": "star50"}


def load_all():
    fd = pd.read_parquet("data/fund_day.parquet")
    ix = pd.read_csv(f"{P}/index_daily.csv", index_col="date",
                     parse_dates=True)
    sx = pd.read_csv("data/sector_index_real.csv", index_col=0,
                     parse_dates=True)
    return fd, ix, sx


def build_groups(fd, ix, sx):
    uni = pd.read_csv("ETF_UNIVERSE_AND_GROUPS.csv",
                      dtype={"fund_code": str})
    gmap = uni.set_index("fund_code").group.to_dict()
    fd2 = fd[fd.fund_code.isin(gmap)].copy()
    fd2["grp"] = fd2.fund_code.map(gmap)
    fd2 = fd2[fd2.grp != "non_equity"].sort_values(["fund_code", "date"])
    fd2["mv_prev"] = fd2.groupby("fund_code").mv.shift(1)
    fd2["w"] = fd2.mv_prev * fd2.nav_ret
    agg = (fd2.groupby(["grp", "date"])
              .agg(flow=("flow_use", "sum"), aum=("mv", "sum"),
                   flow_strict=("flow_use_strict", "sum"),
                   flow_raw=("flow_yi", "sum"),
                   wnum=("w", "sum"), wden=("mv_prev", "sum"),
                   out_days=("flow_use", lambda s: (s < 0).sum()))
              .reset_index())
    agg["ret"] = agg.wnum / agg.wden
    groups = {}
    for g, sub in agg.groupby("grp"):
        groups[g] = sub.set_index("date").sort_index()
    tot = agg.groupby("date")[["flow", "aum", "wnum", "wden",
                               "flow_strict", "flow_raw",
                               "out_days"]].sum()
    tot["ret"] = tot.wnum / tot.wden
    groups["G1_all_equity"] = tot.sort_index()
    for g, df in groups.items():
        df.index = pd.to_datetime(df.index)
        df["ret_proxy"] = df.ret
        df["hs300"] = ix.hs300.reindex(df.index)
        df["all_a"] = ix.all_a.reindex(df.index)
        if g in REAL_IDX and REAL_IDX[g] in sx.columns:
            df["idx_level"] = sx[REAL_IDX[g]].reindex(df.index)
            df["idx_source"] = "real:" + REAL_IDX[g]
        elif g == "G2_hs300_head":
            df["idx_level"] = df.hs300
            df["idx_source"] = "real:hs300"
        elif g in ("G3_other_broad", "G1_all_equity"):
            df["idx_level"] = df.all_a
            df["idx_source"] = "real:all_a"
        elif g == "G9_sse50_head":
            df["idx_level"] = sx.sse50.reindex(df.index)
            df["idx_source"] = "real:sse50"
        else:
            df["idx_level"] = (1 + df.ret_proxy.fillna(0)).cumprod()
            df["idx_source"] = "proxy:mv_weighted"
        df["ret_idx"] = df.idx_level.pct_change()
        df["ret_mkt"] = df.hs300.pct_change()
    return groups


def factors(df):
    out = df.copy()
    aum = out.aum
    out["i1"] = out.flow / aum.shift(1)
    for w in (5, 10, 20, 40, 60):
        out[f"F{w}"] = out.flow.rolling(w).sum() / aum.shift(w)
    out["outshare20"] = (out.flow < 0).rolling(20).mean()
    out["inshare20"] = (out.flow > 0).rolling(20).mean()
    out["F20_prev"] = out.F20.shift(20)
    out["inflect"] = out.F20 - out.F20_prev
    mu = out.i1.rolling(20).sum().shift(1).rolling(Z_BASE).mean()
    sd = out.i1.rolling(20).sum().shift(1).rolling(Z_BASE).std()
    out["z20"] = (out.i1.rolling(20).sum() - mu) / sd
    px = (1 + out.ret_idx.fillna(0)).cumprod()
    out["_px"] = px
    lr = np.log1p(out.ret_idx.fillna(0))
    arr_px, arr_lr, arr_r = px.values, lr.values, out.ret_idx.fillna(0).values
    n = len(out)
    for w in FWIN:
        fwd = np.full(n, np.nan)
        low = np.full(n, np.nan)
        mdd = np.full(n, np.nan)
        vol = np.full(n, np.nan)
        for t in range(n):
            lo, hi = t + 1, min(n, t + 1 + w)
            if hi - lo < w:
                continue
            seg_px = arr_px[lo:hi]
            fwd[t] = np.expm1(arr_lr[lo:hi].sum())
            low[t] = seg_px.min() / arr_px[t] - 1
            peak = np.maximum.accumulate(seg_px)
            mdd[t] = (seg_px / peak - 1).min()
            vol[t] = arr_r[lo:hi].std() * np.sqrt(244)
        out[f"fwd_ret{w}"] = fwd
        out[f"fwd_low{w}"] = low
        out[f"fwd_mdd{w}"] = mdd
        out[f"fwd_vol{w}"] = vol
    out["idx_ret20"] = out.ret_idx.rolling(20).sum()
    out["vol60"] = out.ret_idx.rolling(60).std()
    return out


def clusters(positions, gap=CLUSTER_GAP):
    """Group index positions into clusters; first position is event day."""
    out = []
    for p in sorted(set(positions)):
        if not out or p - out[-1][-1] >= gap:
            out.append([p])
        else:
            out[-1].append(p)
    return out


def event_sets(df):
    idx = df.index
    m = {
        "outflow": ((df.F20 <= OUT_THR) & (df.outshare20 >= OUTSHARE)),
        "inflow": ((df.F20 >= IN_THR) & (df.inshare20 >= OUTSHARE)),
        "inflect_up": ((df.F20_prev <= OUT_THR) & (df.inflect >= INFLECT_THR)),
        "div_up_out": ((df.idx_ret20 > 0.02) & (df.F20 < 0)),
        "div_dn_in": ((df.idx_ret20 < -0.02) & (df.F20 > 0)),
        "z_out": (df.z20 <= -2),
    }
    res = {}
    for k, mask in m.items():
        pos = np.flatnonzero(mask.fillna(False).values)
        cls = clusters(pos)
        res[k] = {"positions": [c[0] for c in cls],
                  "dates": [idx[c[0]] for c in cls],
                  "n_events": len(pos), "n_clusters": len(cls)}
    return res


def ctrl_pool(df, ev_pos):
    bad = np.zeros(len(df), bool)
    for p in ev_pos:
        bad[max(0, p - 40):p + 60] = True
    ok = df[~bad & df.F20.notna()]
    return ok


def matched_controls(df, ev_pos):
    pool = ctrl_pool(df, ev_pos)
    picks = []
    for p in ev_pos:
        r, v = df.iloc[p][["idx_ret20", "vol60"]]
        cand = pool[(pool.idx_ret20.between(r - 0.03, r + 0.03)) &
                    (pool.vol60.between(v * 0.7, v * 1.3))]
        if len(cand):
            picks.append(cand.index)
    return pool, picks


def resp_curve(df, ev_pos, ctrl_idx_list):
    """Mean forward path (compound ret, fwd mdd, vol) at each horizon 0..120."""
    maxh = 120
    def path_for(pos_list):
        rows = []
        for p in pos_list:
            if p + maxh >= len(df):
                continue
            seg_px = df._px.values[p + 1:p + 1 + maxh] / df._px.values[p]
            seg_r = df.ret_idx.values[p + 1:p + 1 + maxh]
            peak = np.maximum.accumulate(seg_px)
            rows.append({"ret": seg_px - 1,
                         "mdd": seg_px / peak - 1,
                         "vol": pd.Series(seg_r).expanding().std().values
                                * np.sqrt(244)})
        return rows
    ev_paths = path_for(list(ev_pos))
    ctrl_paths = []
    for idx_list in ctrl_idx_list:
        ctrl_paths += path_for(list(df.index.get_indexer(idx_list)))
    rows = []
    hs = list(range(1, maxh + 1))
    for h in hs:
        i = h - 1
        er = np.nanmean([p["ret"][i] for p in ev_paths]) if ev_paths else np.nan
        em = np.nanmean([p["mdd"][i] for p in ev_paths]) if ev_paths else np.nan
        evl = np.nanmean([p["vol"][i] for p in ev_paths]) if ev_paths else np.nan
        cr = np.nanmean([p["ret"][i] for p in ctrl_paths]) if ctrl_paths else np.nan
        cm = np.nanmean([p["mdd"][i] for p in ctrl_paths]) if ctrl_paths else np.nan
        rows.append({"h": h, "ev_ret": er, "ctrl_ret": cr,
                     "ev_mdd": em, "ctrl_mdd": cm, "ev_vol": evl,
                     "n_ev": len(ev_paths), "n_ctrl": len(ctrl_paths)})
    return pd.DataFrame(rows)


def event_stats(df, ev_pos, pool):
    rows = []
    for w in FWIN:
        ev = df.iloc[list(ev_pos)]
        m_evr, m_low, m_mdd = ev[f"fwd_ret{w}"], ev[f"fwd_low{w}"], ev[f"fwd_mdd{w}"]
        a = pool
        evr, evl, evm = m_evr.dropna(), m_low.dropna(), m_mdd.dropna()
        if len(evr) < 3:
            continue
        n = len(evm)
        rng = np.random.default_rng(w)
        rep = [np.nanmean(evm.values[rng.integers(0, n, n)]) for _ in range(400)]
        lo, hi = np.nanpercentile(rep, [5, 95])
        rows.append({
            "window": w, "n": n,
            "ev_ret": round(evr.mean(), 4),
            "all_ret": round(a[f"fwd_ret{w}"].mean(), 4),
            "ev_low": round(evl.mean(), 4),
            "all_low": round(a[f"fwd_low{w}"].mean(), 4),
            "ev_mdd": round(evm.mean(), 4),
            "all_mdd": round(a[f"fwd_mdd{w}"].mean(), 4),
            "p_low_le5": round((evl <= -0.05).mean(), 3),
            "all_p_low_le5": round((a[f"fwd_low{w}"] <= -0.05).mean(), 3),
            "p_low_le10": round((evl <= -0.10).mean(), 3),
            "all_p_low_le10": round((a[f"fwd_low{w}"] <= -0.10).mean(), 3),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)})
    return rows


def backtest(df, signal_mask):
    """signal_mask: boolean Series on day-t data -> exit at t+1."""
    ret = df.ret_mkt.fillna(0).values
    px = df._px.values
    mom = df.ret_mkt.rolling(20).sum().values
    ma = df._px.rolling(200).mean().values
    sig = signal_mask.fillna(False).values
    n = len(df)
    posB_raw = ((mom > 0) & (px > ma)).astype(float)
    posC_raw = np.zeros(n)
    posC_raw[0] = posB_raw[0]
    for t in range(1, n):
        if sig[t]:
            posC_raw[t] = 0.0
        elif posB_raw[t] == 1:
            posC_raw[t] = 1.0
        else:
            posC_raw[t] = posC_raw[t - 1]
    posB = np.roll(posB_raw, 1); posB[0] = 0
    posC = np.roll(posC_raw, 1); posC[0] = 0
    # alignment assertions
    assert np.allclose(posB[1:], posB_raw[:-1]), "posB not single-lagged"
    assert np.allclose(posC[1:], posC_raw[:-1]), "posC not single-lagged"
    assert set(np.unique(posC)) <= {0.0, 1.0}
    trades = []
    dates = df.index
    for name, pos in (("B", posB), ("C", posC)):
        sw = np.diff(np.concatenate([[0], pos]))
        for t in np.flatnonzero(sw):
            trades.append({"strategy": name, "exec_date": str(dates[t])[:10],
                           "signal_date": str(dates[t - 1])[:10],
                           "to_pos": pos[t],
                           "F20_sig": round(df.F20.iloc[t - 1], 5),
                           "z20_sig": round(df.z20.iloc[t - 1], 3)})
    def stats(pos, name):
        sw = np.abs(np.diff(np.concatenate([[0], pos])))
        r = pos * ret - sw * COST
        eq = np.cumprod(1 + r)
        mdd = (eq / np.maximum.accumulate(eq) - 1).min()
        yrs = n / 244
        ann = eq[-1] ** (1 / yrs) - 1
        vol = np.nanstd(r) * np.sqrt(244)
        dd = np.nanstd(np.minimum(r, 0)) * np.sqrt(244)
        return {"strategy": name, "ann_ret": round(ann, 4),
                "vol": round(vol, 4), "max_dd": round(mdd, 4),
                "down_dev": round(dd, 4),
                "calmar": round(ann / abs(mdd), 3) if mdd else np.nan,
                "turnover": round(sw.sum(), 1),
                "n_trades": int((sw > 0).sum()),
                "pct_flat": round((pos == 0).mean(), 3),
                "final_eq": round(eq[-1], 3)}
    return [stats(np.ones(n), "A_hold_index"), stats(posB, "B_price_risk"),
            stats(posC, "C_price_plus_flow")], pd.DataFrame(trades)


def main():
    fd, ix, sx = load_all()
    groups = build_groups(fd, ix, sx)
    fdata = {g: factors(df) for g, df in groups.items()}

    ev_rows, resp_rows, lag_rows, regime_rows, oos = [], [], [], [], []
    for g, df in fdata.items():
        es = event_sets(df)
        for kind, e in es.items():
            pool, picks = matched_controls(df, e["positions"])
            rc = resp_curve(df, e["positions"], picks)
            for _, r in rc.iterrows():
                resp_rows.append({"group": g, "kind": kind, **r.to_dict()})
            for r in event_stats(df, e["positions"], pool):
                ev_rows.append({"group": g, "kind": kind,
                                "n_clusters": e["n_clusters"],
                                "n_signal_days": e["n_events"], **r})
        z = df.dropna(subset=["F20"])
        for w in (20, 40, 60, 120):
            lag_rows.append({
                "group": g, "fwd_window": w,
                "corr_F20_fwdret": round(z.F20.corr(z[f"fwd_ret{w}"]), 4),
                "corr_F20_fwdlow": round(z.F20.corr(z[f"fwd_low{w}"]), 4),
                "corr_idxret20_fwdF20": round(
                    z.idx_ret20.corr(z.F20.shift(-w).shift(-(w - 1))), 4),
                "n": len(z)})
        for lab, mm in (("hi_vol", z.vol60 > z.vol60.median()),
                        ("lo_vol", z.vol60 <= z.vol60.median()),
                        ("up20", z.idx_ret20 > 0), ("dn20", z.idx_ret20 <= 0)):
            sub = z[mm]
            regime_rows.append({"group": g, "regime": lab, "n": len(sub),
                                "corr_F20_fwdret40": round(
                                    sub.F20.corr(sub.fwd_ret40), 4)})
        for lab, sub in (("train", z[z.index < "2024-01-01"]),
                         ("oos", z[z.index >= "2024-01-01"])):
            if len(sub) > 100:
                oos.append({"group": g, "seg": lab, "n": len(sub),
                            "corr_F20_fwdret40": round(
                                sub.F20.corr(sub.fwd_ret40), 4),
                            "corr_F20_fwdret60": round(
                                sub.F20.corr(sub.fwd_ret60), 4),
                            "corr_F20_fwdret120": round(
                                sub.F20.corr(sub.fwd_ret120), 4)})

    pd.DataFrame(lag_rows).to_csv("FLOW_RETURN_LAG_ANALYSIS.csv", index=False)
    pd.DataFrame(ev_rows).to_csv("EVENT_STUDY_RESULTS.csv", index=False)
    pd.DataFrame(resp_rows).to_csv("RESPONSE_CURVES.csv", index=False)
    pd.DataFrame(regime_rows).to_csv("REGIME_COMPARISON.csv", index=False)
    pd.DataFrame(oos).to_csv("OOS_VALIDATION.csv", index=False)

    # corp sensitivity: unverified-masked variant on G2/G1
    sens = []
    for g in ("G2_hs300_head", "G1_all_equity"):
        base = fdata[g].copy()
        for lab, col in (("main_confirmed_algosplit", "flow"),
                         ("strict_add_unverified", "flow_strict")):
            dfv = base.copy()
            dfv["flow"] = dfv[col].fillna(0)
            dfv = factors(dfv)
            e = event_sets(dfv)["outflow"]
            sens.append({"group": g, "variant": lab,
                         "n_clusters": e["n_clusters"],
                         "dates": ";".join(str(x)[:10] for x in e["dates"])})
    pd.DataFrame(sens).to_csv("SENSITIVITY_CORP_ACTION.csv", index=False)

    # backtest on G2, exit = sustained outflow cluster signal
    sig = (fdata["G2_hs300_head"].F20 <= OUT_THR) & \
          (fdata["G2_hs300_head"].outshare20 >= OUTSHARE)
    bt, trades = backtest(fdata["G2_hs300_head"], sig)
    pd.DataFrame(bt).to_csv("RISK_MANAGEMENT_BACKTEST.csv", index=False)
    trades.to_csv("BACKTEST_TRADE_LOG.csv", index=False)
    print(json.dumps(bt, ensure_ascii=False))

    for g, df in fdata.items():
        df.to_parquet(f"data/factors_{g}.parquet")
    print("done")


if __name__ == "__main__":
    main()
