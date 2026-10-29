"""R2.1 risk-warning pipeline. Rules fixed in PRE_REGISTERED_RULES.json."""
import json, sys
import numpy as np
import pandas as pd

sys.path.insert(0, "../etf_flow_r1")
from analyze_r1 import clusters  # noqa

R1D = "../etf_flow_r2/data"   # r2 parquets include accel/streaks/policy cols
RULES = json.load(open("PRE_REGISTERED_RULES.json"))
FWIN = RULES["forward_windows"]
W = RULES["scores"]["weights"]
STATES = ["NORMAL", "WATCH", "ELEVATED", "HIGH_PRESSURE", "RECOVERING"]


def pctl_exp(s, min_p=252):
    """Expanding-window percentile rank (0-100), PIT."""
    arr = s.values
    out = np.full(len(arr), np.nan)
    for i in range(len(arr)):
        if i < min_p or np.isnan(arr[i]):
            continue
        w = arr[:i + 1]
        w = w[~np.isnan(w)]
        out[i] = (w <= arr[i]).mean() * 100
    return pd.Series(out, index=s.index)


def load():
    groups = {}
    for p in __import__("pathlib").Path(R1D).glob("factors_*.parquet"):
        g = p.stem.replace("factors_", "")
        d = pd.read_parquet(p)
        d.index = pd.to_datetime(d.index)
        groups[g] = d
    fd = pd.read_parquet("../etf_flow_r1/data/fund_day.parquet")
    uni = pd.read_csv("../etf_flow_r1/ETF_UNIVERSE_AND_GROUPS.csv",
                      dtype={"fund_code": str})
    pe = pd.read_csv("../etf_flow_r2/POLICY_EVENTS.csv")
    return groups, fd, uni, pe


def add_breadth(groups, fd, uni):
    gmap = uni.set_index("fund_code").group.to_dict()
    f = fd[fd.fund_code.isin(gmap)].copy()
    f["grp"] = f.fund_code.map(gmap)
    f = f[f.grp != "non_equity"]
    f["out_mv"] = np.where(f.flow_use < 0, f.mv, 0.0)
    f["in_mv"] = np.where(f.flow_use > 0, f.mv, 0.0)
    br = (f.groupby(["grp", "date"])
            .agg(out_aum=("out_mv", "sum"), in_aum=("in_mv", "sum"),
                 tot_aum=("mv", "sum"), n_out=("flow_use",
                                              lambda s: (s < 0).sum()),
                 n=("flow_use", "size")).reset_index())
    for g, d in groups.items():
        b = br[br.grp == g].set_index("date")
        d["breadth_out"] = (b.out_aum / b.tot_aum).reindex(d.index)
        d["breadth_in"] = (b.in_aum / b.tot_aum).reindex(d.index)
        d["n_out_share"] = (b.n_out / b.n).reindex(d.index)
        d["outshare40"] = (d.flow < 0).rolling(40).mean()
        d["inshare40"] = (d.flow > 0).rolling(40).mean()
    return groups


def scores(df):
    d = df.copy()
    d["wp_raw"] = (W["F20"] * pctl_exp(-d.F20) +
                   W["share"] * pctl_exp(d.outshare20) +
                   W["F40"] * pctl_exp(-d.F40) +
                   W["accel"] * pctl_exp(-d.accel))
    d["as_raw"] = (W["F20"] * pctl_exp(d.F20) +
                   W["share"] * pctl_exp(d.inshare20) +
                   W["F40"] * pctl_exp(d.F40) +
                   W["accel"] * pctl_exp(d.accel))
    # fallback when accel NaN early: renormalize on available parts
    d["WP"] = d.wp_raw
    d["AS"] = d.as_raw
    return d


def state_machine(df):
    wp, as_ = df.WP.fillna(0).values, df.AS.fillna(0).values
    o40 = df.outshare40.fillna(0).values
    n = len(df)
    state = ["NORMAL"] * n
    cur = "NORMAL"
    hold = 0
    last_hi = -10 ** 9
    rec_days = 0
    def upd(i, target, cond):
        nonlocal cur, hold
        if cond:
            hold += 1
        else:
            hold = 0
        need = 5 if STATES.index(target) > STATES.index("NORMAL") else 10
        if hold >= need:
            cur = target
            hold = 0
    for i in range(n):
        if wp[i] >= 70:
            last_hi = i
        if cur == "NORMAL":
            upd(i, "WATCH", wp[i] >= 70)
            if as_[i] >= 65:
                upd(i, "RECOVERING", True)
        elif cur == "WATCH":
            upd(i, "ELEVATED", wp[i] >= 80)
            if wp[i] < 60 and last_hi >= i - 40:
                upd(i, "RECOVERING", True)
        elif cur == "ELEVATED":
            upd(i, "HIGH_PRESSURE",
                wp[i] >= 85 or (wp[i] >= 75 and o40[i] >= 0.6))
            if wp[i] < 60:
                upd(i, "RECOVERING", True)
        elif cur == "HIGH_PRESSURE":
            if wp[i] < 60:
                upd(i, "RECOVERING", True)
        elif cur == "RECOVERING":
            if wp[i] >= 70:
                upd(i, "WATCH", True)
            elif wp[i] < 60:
                rec_days += 1
                if rec_days >= 20:
                    cur = "NORMAL"
                    rec_days = 0
            else:
                rec_days = 0
        if cur != "RECOVERING":
            rec_days = 0
        state[i] = cur
    df["state"] = state
    return df


def transitions(df):
    rows = []
    prev = df.state.iloc[0]
    for i in range(1, len(df)):
        if df.state.iloc[i] != prev:
            rows.append({"date": str(df.index[i])[:10],
                         "from": prev, "to": df.state.iloc[i],
                         "WP": round(df.WP.iloc[i], 1),
                         "AS": round(df.AS.iloc[i], 1),
                         "F20": round(df.F20.iloc[i], 4),
                         "F40": round(df.F40.iloc[i], 4),
                         "outshare20": round(df.outshare20.iloc[i], 2),
                         "breadth_out": round(df.breadth_out.iloc[i], 3),
                         "neg_streak": int(df.neg_streak.iloc[i]),
                         "price_confirm": bool(
                             df.ret_idx.iloc[i] < 0)})
            prev = df.state.iloc[i]
    return rows


def fwd_stats(df, pos, pool, kind, level):
    rows = []
    for w in FWIN:
        ev = df.iloc[pos]
        er, el, em, evo = (ev[f"fwd_ret{w}"].dropna(), ev[f"fwd_low{w}"].dropna(),
                           ev[f"fwd_mdd{w}"].dropna(), ev[f"fwd_vol{w}"].dropna())
        if len(er) < 3:
            continue
        n = len(em)
        rng = np.random.default_rng(w)
        rep = [np.nanmean(em.values[rng.integers(0, n, n)]) for _ in range(300)]
        lo, hi = np.nanpercentile(rep, [5, 95])
        rows.append({"group": kind, "state": level, "window": w,
                     "n": n,
                     "ev_ret": round(er.mean(), 4),
                     "all_ret": round(pool[f"fwd_ret{w}"].mean(), 4),
                     "ev_low": round(el.mean(), 4),
                     "all_low": round(pool[f"fwd_low{w}"].mean(), 4),
                     "ev_mdd": round(em.mean(), 4),
                     "all_mdd": round(pool[f"fwd_mdd{w}"].mean(), 4),
                     "ev_vol": round(evo.mean(), 4),
                     "p_dd5": round((el <= -0.05).mean(), 3),
                     "p_dd10": round((el <= -0.10).mean(), 3),
                     "p_dd15": round((el <= -0.15).mean(), 3),
                     "all_p_dd10": round((pool[f"fwd_low{w}"] <= -0.10).mean(), 3),
                     "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)})
    return rows


def risk_episodes(df, thr):
    """Onset days where fwd_mdd60 crosses below thr (clustered)."""
    m = df.fwd_mdd60 <= thr
    pos = np.flatnonzero(m.fillna(False).values)
    cls = clusters(list(pos))
    return [c[0] for c in cls]


def lead_time(df, onsets, warn_pos):
    rows = []
    covered = 0
    for p in onsets:
        prior = [q for q in warn_pos if q <= p]
        first = prior[0] if prior else None
        if first is not None and p - first <= 60:
            covered += 1
            rows.append({"onset": str(df.index[p])[:10],
                         "warn_start": str(df.index[first])[:10],
                         "lead_days": p - first,
                         "mkt_fell_before_warn": round(
                             df._px.iloc[first] /
                             df._px.iloc[max(0, first - 60):first].max() - 1, 4),
                         "covered": True})
        else:
            rows.append({"onset": str(df.index[p])[:10],
                         "warn_start": "", "lead_days": np.nan,
                         "mkt_fell_before_warn": np.nan, "covered": False})
    return rows, covered / max(1, len(onsets))


def pr_auc(y, s):
    """Average precision + ROC-ish via simple sort."""
    o = np.argsort(-s)
    y = np.asarray(y)[o]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    rec = tp / max(1, y.sum())
    ap = np.trapezoid(prec * np.diff(np.concatenate([[0], rec])) >= 0,
                      rec) if len(rec) > 1 else np.nan
    # average precision proper
    ap = float((prec * y).sum() / max(1, y.sum()))
    return ap


def logistic_fit(X, y, lr=0.05, iters=800):
    Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)
    w = np.zeros(X.shape[1] + 1)
    Xb = np.c_[np.ones(len(Xs)), Xs]
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w))
        w -= lr * Xb.T @ (p - y) / len(y)
    return w, X.mean(0), X.std(0) + 1e-9


def logistic_pred(w, mu, sd, X):
    Xb = np.c_[np.ones(len(X)), (X - mu) / sd]
    return 1 / (1 + np.exp(-Xb @ w))


def main():
    groups, fd, uni, pe = load()
    groups = add_breadth(groups, fd, uni)
    off = pe[pe.category.isin(["official_action", "official_document"])]
    pdates = pd.to_datetime(off.event_date)

    for g, d in groups.items():
        d = scores(d)
        d = state_machine(d)
        flag = np.zeros(len(d), bool)
        for pd_ in pdates:
            j = d.index.searchsorted(pd_)
            flag[j:j + 60] = True
        d["policy_on"] = flag
        groups[g] = d
        d.to_parquet(f"data/factors_{g}.parquet")

    g2 = groups["G2_hs300_head"]

    # ETF_GROUP_MEMBERSHIP + normalized factors dump
    uni[uni.group != "non_equity"].to_csv("ETF_GROUP_MEMBERSHIP.csv",
                                          index=False)
    nf = g2[["flow", "aum", "F5", "F10", "F20", "F40", "F60",
             "outshare20", "inshare20", "breadth_out", "breadth_in",
             "accel", "WP", "AS", "state", "hs300"]].copy()
    nf.index = nf.index.strftime("%Y-%m-%d")
    nf.to_csv("NORMALIZED_FLOW_FACTORS.csv")

    # state daily ledger + transitions
    ledger = g2[["WP", "AS", "F20", "F40", "F60", "outshare20",
                 "breadth_out", "neg_streak", "state", "hs300",
                 "policy_on"]].copy()
    ledger.index = ledger.index.strftime("%Y-%m-%d")
    ledger.to_csv("WARNING_STATE_DAILY.csv")
    tr = transitions(g2)
    pd.DataFrame(tr).to_csv("WARNING_TRANSITIONS.csv", index=False)

    # forward risk by state (first-entry events per state level)
    fr_rows = []
    warn_lv = {"WATCH": ["WATCH", "ELEVATED", "HIGH_PRESSURE"],
               "ELEVATED_plus": ["ELEVATED", "HIGH_PRESSURE"],
               "HIGH_PRESSURE": ["HIGH_PRESSURE"],
               "RECOVERING": ["RECOVERING"]}
    for lab, lv in warn_lv.items():
        mask = g2.state.isin(lv)
        pos = np.flatnonzero(mask.values)
        cls = clusters(list(pos))
        ev = [c[0] for c in cls]
        bad = np.zeros(len(g2), bool)
        for p in ev:
            bad[max(0, p - 40):p + 60] = True
        pool = g2[~bad & g2.F20.notna()]
        fr_rows += fwd_stats(g2, ev, pool, "G2_hs300_head", lab)
    pd.DataFrame(fr_rows).to_csv("FORWARD_RISK_BY_STATE.csv", index=False)

    # risk episodes + lead time + coverage
    warn_mask = g2.state.isin(["WATCH", "ELEVATED", "HIGH_PRESSURE"])
    warn_pos = np.flatnonzero(warn_mask.values)
    warn_starts = [c[0] for c in clusters(list(warn_pos), gap=10)]
    lt_rows = []
    cov = {}
    for thr, lab in [(-0.10, "dd10"), (-0.15, "dd15")]:
        ons = risk_episodes(g2, thr)
        rows, c = lead_time(g2, ons, warn_starts)
        for r in rows:
            r["event"] = lab
            lt_rows.append(r)
        cov[lab] = round(c, 3)
    pd.DataFrame(lt_rows).to_csv("ALERT_LEAD_TIME.csv", index=False)

    # false alerts: warning clusters with no dd10 within 120d
    fa = []
    for c in clusters(list(warn_pos), gap=10):
        s, e = c[0], c[-1]
        lo60 = g2.fwd_low120.iloc[s]
        r120 = g2.fwd_ret120.iloc[s]
        dur = e - s
        fa.append({"start": str(g2.index[s])[:10],
                   "end": str(g2.index[e])[:10],
                   "dur_days": dur, "state_peak": g2.state.iloc[c].mode()[0],
                   "WP_peak": round(g2.WP.iloc[c].max(), 1),
                   "fwd_low120": round(lo60, 4) if pd.notna(lo60) else np.nan,
                   "fwd_ret120": round(r120, 4) if pd.notna(r120) else np.nan,
                   "false_alert": bool(pd.notna(lo60) and lo60 > -0.10)})
    pd.DataFrame(fa).to_csv("FALSE_ALERT_AUDIT.csv", index=False)

    # A/B/C incremental value vs dd10-in-60d label
    y = (g2.fwd_mdd60 <= -0.10).astype(float).values
    volp = pctl_exp(g2.vol60)
    warnA = ((g2.ret_idx.rolling(20).sum() <= -0.03) | (volp >= 80)).values
    warnB = (g2.WP >= 70).values
    warnC = warnA | warnB
    valid = ~np.isnan(y) & ~np.isnan(g2.WP.values) & ~np.isnan(volp.values)
    tr_m = valid & (g2.index < "2024-01-01")
    iv = []
    for nm, w in [("A_price", warnA), ("B_flow", warnB), ("C_AB", warnC)]:
        wv = w & valid
        tp = ((wv == 1) & (y == 1)).sum()
        fp_ = ((wv == 1) & (y == 0)).sum()
        fn = ((wv == 0) & (y == 1)).sum()
        prec = tp / max(1, tp + fp_)
        rec = tp / max(1, tp + fn)
        # mean lead among covered onsets
        ons = risk_episodes(g2, -0.10)
        starts = [c[0] for c in clusters(list(np.flatnonzero(wv)), gap=10)]
        covd = [p for p in ons if any(q <= p and p - q <= 60 for q in starts)]
        iv.append({"model": nm, "n_warn_days": int(wv.sum()),
                   "precision": round(prec, 3), "recall": round(rec, 3),
                   "risk_coverage": round(len(covd) / max(1, len(ons)), 3),
                   "fpr": round((wv & (y == 0)).mean(), 3)})
    # calibrated probs: features [WP, volp, idx_ret20]
    X = np.c_[g2.WP.fillna(0).values, volp.fillna(50).values,
              g2.ret_idx.rolling(20).sum().fillna(0).values]
    wB, muB, sdB = logistic_fit(X[tr_m][:, [1, 2]], y[tr_m])
    wC, muC, sdC = logistic_fit(X[tr_m], y[tr_m])
    pA = logistic_pred(wB, muB, sdB, X[:, [1, 2]])
    pC = logistic_pred(wC, muC, sdC, X)
    pB = g2.WP.fillna(0).values / 100
    for nm, p in [("A_price", pA), ("B_flow", pB), ("C_AB", pC)]:
        pv = p[valid]
        yv = y[valid]
        brier = np.mean((pv - yv) ** 2)
        base = np.mean((yv.mean() - yv) ** 2)
        for r in iv:
            if r["model"] == nm:
                r["ap"] = round(pr_auc(yv, pv), 3)
                r["brier"] = round(brier, 4)
                r["brier_skill"] = round(1 - brier / base, 4)
    # OOS segments
    for r in iv:
        wfull = (warnA if r["model"] == "A_price" else
                 warnB if r["model"] == "B_flow" else warnC)
        for lab, m in [("valid_24_25",
                        (g2.index >= "2024-01-01") & (g2.index < "2026-01-01")),
                       ("touched_26", g2.index >= "2026-01-01")]:
            sel = valid & m
            wm, yv = wfull[sel], y[sel]
            tp = ((wm == 1) & (yv == 1)).sum()
            r[f"recall_{lab}"] = round(tp / max(1, (yv == 1).sum()), 3)
    pd.DataFrame(iv).to_csv("INCREMENTAL_VALUE_VS_PRICE.csv", index=False)

    # H3 tech: own WP vs G2 WP on own-index fwd_mdd60
    tech = []
    g2wp = g2.WP.reindex(g2.index)
    for g in ["G4k_star", "G5_semiconductor", "G6_ai_compute",
              "G7_robot", "G8_softinfo"]:
        d = groups[g]
        own = d.WP.corr(d.fwd_mdd60)
        cross = g2wp.reindex(d.index).corr(d.fwd_mdd60)
        tech.append({"group": g, "idx_source": str(d.idx_source.iloc[0]),
                     "corr_ownWP_ownMDD": round(own, 4),
                     "corr_G2WP_ownMDD": round(cross, 4),
                     "n": int(d.WP.notna().sum())})
    pd.DataFrame(tech).to_csv("TECHNOLOGY_WARNING_RESULTS.csv", index=False)

    # policy regime
    pol = []
    for lab, m in [("policy_on", g2.policy_on), ("policy_off", ~g2.policy_on)]:
        sub = g2[m]
        pol.append({"segment": lab, "n": len(sub),
                    "warn_days": int(sub.state.isin(
                        ["WATCH", "ELEVATED", "HIGH_PRESSURE"]).sum()),
                    "corr_WP_fwdmdd60": round(sub.WP.corr(sub.fwd_mdd60), 4),
                    "corr_WP_fwdret60": round(sub.WP.corr(sub.fwd_ret60), 4)})
    pd.DataFrame(pol).to_csv("POLICY_REGIME_RESULTS.csv", index=False)
    print("coverage:", cov)
    print(json.dumps(iv, ensure_ascii=False))
    print("done")


if __name__ == "__main__":
    main()
