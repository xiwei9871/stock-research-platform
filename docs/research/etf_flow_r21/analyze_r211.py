"""R2.1.1 targeted fixes: lead time, risk-event defs, censoring, calibration,
state-machine conformance. Reads r21 factors (WP/AS unchanged)."""
import numpy as np
import pandas as pd
import json

sys_path = __import__("sys"); sys_path.path.insert(0, "../etf_flow_r1")
from analyze_r1 import clusters  # noqa

RULES = json.load(open("PRE_REGISTERED_RULES.json"))
WARN = {"WATCH", "ELEVATED", "HIGH_PRESSURE"}
FWIN = RULES["forward_windows"]


def state_machine(df):
    """Per-condition counters; hold days per PRE_REGISTERED_RULES.json.
    Bug fixes vs r21: shared `hold` counter removed; HIGH entry 10d (was 5d);
    AS>=65->RECOVERING 10d (was 5d); RECOVERING->NORMAL WP<60 10d (was 20d)."""
    wp = df.WP.fillna(0).values
    as_ = df.AS.fillna(0).values
    o40 = df.outshare40.fillna(0).values
    n = len(df)
    state = ["NORMAL"] * n
    cur = "NORMAL"
    last_hi = -10**9
    c = {}  # condition -> consecutive days

    def tick(key, cond):
        c[key] = c.get(key, 0) + 1 if cond else 0
        return c[key]
    for i in range(n):
        if wp[i] >= 70:
            last_hi = i
        if cur == "NORMAL":
            if tick("w", wp[i] >= 70) >= 5:
                cur = "WATCH"
            elif tick("r", as_[i] >= 65) >= 10:
                cur = "RECOVERING"
        elif cur == "WATCH":
            if tick("e", wp[i] >= 80) >= 5:
                cur = "ELEVATED"
            elif tick("r", wp[i] < 60 and last_hi >= i - 40) >= 5:
                cur = "RECOVERING"
        elif cur == "ELEVATED":
            if tick("h", wp[i] >= 85 or (wp[i] >= 75 and o40[i] >= 0.6)) >= 10:
                cur = "HIGH_PRESSURE"
            elif tick("r", wp[i] < 60) >= 5:
                cur = "RECOVERING"
        elif cur == "HIGH_PRESSURE":
            if tick("r", wp[i] < 60) >= 5:
                cur = "RECOVERING"
        elif cur == "RECOVERING":
            if tick("w", wp[i] >= 70) >= 5:
                cur = "WATCH"
            elif tick("n", wp[i] < 60) >= 10:
                cur = "NORMAL"
        state[i] = cur
    df = df.copy()
    df["state"] = state
    return df


def transitions(df):
    rows, prev = [], df.state.iloc[0]
    for i in range(1, len(df)):
        if df.state.iloc[i] != prev:
            rows.append({"date": str(df.index[i])[:10], "from": prev,
                         "to": df.state.iloc[i], "WP": round(df.WP.iloc[i], 1),
                         "F20": round(df.F20.iloc[i], 4),
                         "outshare20": round(df.outshare20.iloc[i], 2),
                         "price_confirm": bool(df.ret_idx.iloc[i] < 0)})
            prev = df.state.iloc[i]
    return rows


def realized_onsets(df, thr, lookback=120, min_out=20):
    """First day price path enters drawdown state (px <= (1+thr)*rolling peak)
    after >= min_out days outside. Returns onset positions + episode info."""
    px = df._px.values
    peak = df._px.rolling(lookback, min_periods=20).max().values
    dd = px / peak - 1
    inst = dd <= thr
    onsets = []
    i = 0
    while i < len(df):
        if inst[i] and (i == 0 or not inst[:i][-min_out:].any()):
            trough = i + int(np.nanargmin(dd[i:i + 120])) if i < len(dd) else i
            pk_lo = max(0, i - lookback)
            pk_i = pk_lo + int(np.argmax(px[pk_lo:i + 1]))
            onsets.append({"i": i, "onset": df.index[i],
                           "peak_date": df.index[pk_i],
                           "peak_px": px[pk_i],
                           "trough_i": min(trough, len(df) - 1)})
            # skip until exits state
            j = i
            while j < len(df) and inst[j]:
                j += 1
            i = j
        else:
            i += 1
    for o in onsets:
        o["trough_date"] = df.index[o["trough_i"]]
        o["depth"] = round(px[o["trough_i"]] / o["peak_px"] - 1, 4)
        o["right_censored"] = bool(o["trough_i"] >= len(df) - 5)
    return onsets, dd


def lead_for_onset(onset_i, warn_cl, upgrades):
    """All warning cluster starts / upgrades within prior 60d of onset."""
    lo = onset_i - 60
    ws = [c for c in warn_cl if lo <= c[0] <= onset_i]
    ups = [u for u in upgrades if lo <= u <= onset_i]
    if not ws:
        return {"first_warn_i": None, "last_warn_i": None,
                "upgrade_i": ups[0] if ups else None}
    return {"first_warn_i": ws[0][0], "last_warn_i": ws[-1][0],
            "upgrade_i": ups[0] if ups else None}


def fwd_stats_censored(df, pos, pool, level):
    rows = []
    for w in FWIN:
        ev = df.iloc[pos]
        censored = int((df.index[len(df) - 1] -
                        pd.Series(ev.index)).dt.days.lt(w * 1.5).sum())
        er, el, em = (ev[f"fwd_ret{w}"].dropna(), ev[f"fwd_low{w}"].dropna(),
                      ev[f"fwd_mdd{w}"].dropna())
        if len(em) < 3:
            continue
        rows.append({"state": level, "window": w, "n": len(em),
                     "n_censored": censored,
                     "ev_ret": round(er.mean(), 4),
                     "all_ret": round(pool[f"fwd_ret{w}"].mean(), 4),
                     "ev_low": round(el.mean(), 4),
                     "all_low": round(pool[f"fwd_low{w}"].mean(), 4),
                     "ev_mdd": round(em.mean(), 4),
                     "all_mdd": round(pool[f"fwd_mdd{w}"].mean(), 4),
                     "p_dd10": round((el <= -0.10).mean(), 3),
                     "all_p_dd10": round((pool[f"fwd_low{w}"] <= -0.10).mean(), 3)})
    return rows


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


def pr_ap(y, s):
    o = np.argsort(-np.asarray(s))
    yv = np.asarray(y)[o]
    tp = np.cumsum(yv)
    prec = tp / np.arange(1, len(yv) + 1)
    return float((prec * yv).sum() / max(1, yv.sum()))


def main():
    g2 = pd.read_parquet("data/factors_G2_hs300_head.parquet")
    g2.index = pd.to_datetime(g2.index)
    g2["_px"] = g2.hs300
    g2["state_old"] = g2.state
    g2 = state_machine(g2)
    diff_days = int((g2.state != g2.state_old).sum())
    print("state days changed:", diff_days)

    pd.DataFrame(transitions(g2)).to_csv("WARNING_TRANSITIONS.csv", index=False)
    led = g2[["WP", "AS", "F20", "F40", "F60", "outshare20", "neg_streak",
              "state", "state_old", "hs300", "policy_on"]].copy()
    led.index = led.index.strftime("%Y-%m-%d")
    led.to_csv("WARNING_STATE_DAILY.csv")

    warn_mask = g2.state.isin(WARN)
    warn_cl = clusters(list(np.flatnonzero(warn_mask.values)), gap=10)
    upg = np.flatnonzero(((g2.state == "ELEVATED") |
                          (g2.state == "HIGH_PRESSURE")).values &
                         (~g2.state.shift(1).isin(WARN)).values |
                         ((g2.state == "HIGH_PRESSURE").values &
                          (g2.state.shift(1) == "ELEVATED").values))

    # --- realized risk events + forward labels ---
    led_rows, path_rows = [], []
    cov = {}
    for thr, lab in [(-0.10, "dd10"), (-0.15, "dd15")]:
        ons, dd = realized_onsets(g2, thr)
        hits = 0
        for k, o in enumerate(ons):
            L = lead_for_onset(o["i"], warn_cl, list(upg))
            row = {"event_id": f"{lab}_{k}", "label": lab,
                   "peak": str(o["peak_date"])[:10],
                   "onset": str(o["onset"])[:10],
                   "trough": str(o["trough_date"])[:10],
                   "depth": o["depth"],
                   "right_censored": o["right_censored"],
                   "covered": L["first_warn_i"] is not None}
            for kk in ("first_warn_i", "last_warn_i", "upgrade_i"):
                vi = L[kk]
                row[kk.replace("_i", "")] = (str(g2.index[vi])[:10]
                                           if vi is not None else "")
                row[kk.replace("_i", "_lead")] = (o["i"] - vi
                                                if vi is not None else np.nan)
            row["mkt_dd_at_first_warn"] = (round(dd[L["first_warn_i"]], 4)
                                         if L["first_warn_i"] is not None
                                         else np.nan)
            led_rows.append(row)
            if row["covered"]:
                hits += 1
            lo = max(0, o["i"] - 40)
            for j in range(lo, min(len(g2), o["i"] + 80)):
                path_rows.append({"event_id": f"{lab}_{k}",
                                  "rel_day": j - o["i"],
                                  "date": str(g2.index[j])[:10],
                                  "px": round(g2._px.iloc[j] /
                                              g2._px.iloc[o["i"]], 4)})
        cov[lab] = {"n_events": len(ons), "covered": hits,
                    "coverage": round(hits / max(1, len(ons)), 3)}
    pd.DataFrame(led_rows).to_csv("RISK_EVENT_LEDGER.csv", index=False)
    pd.DataFrame(path_rows).to_csv("EVENT_PRICE_PATHS.csv", index=False)
    print("coverage:", cov)

    # --- revised forward risk by state (censored-aware) ---
    fr_rows = []
    for lab2, lv in {"WATCH": ["WATCH"], "ELEVATED_plus": ["ELEVATED",
                     "HIGH_PRESSURE"], "HIGH_PRESSURE": ["HIGH_PRESSURE"],
                     "RECOVERING": ["RECOVERING"]}.items():
        pos = np.flatnonzero(g2.state.isin(lv).values)
        ev = [c[0] for c in clusters(list(pos))]
        bad = np.zeros(len(g2), bool)
        for p in ev:
            bad[max(0, p - 40):p + 60] = True
        pool = g2[~bad & g2.F20.notna()]
        fr_rows += fwd_stats_censored(g2, ev, pool, lab2)
    pd.DataFrame(fr_rows).to_csv("FORWARD_RISK_BY_STATE.csv", index=False)

    # --- revised false alerts (warn cluster -> dd10 onset within 120d) ---
    fa = []
    onset10 = [o["i"] for o in realized_onsets(g2, -0.10)[0]]
    for c in warn_cl:
        s, e = c[0], c[-1]
        fut = [o for o in onset10 if s < o <= s + 120]
        truncated = s + 120 > len(g2) - 1
        fa.append({"start": str(g2.index[s])[:10],
                   "end": str(g2.index[e])[:10], "dur_days": e - s,
                   "state_peak": g2.state.iloc[c].mode()[0],
                   "WP_peak": round(g2.WP.iloc[c].max(), 1),
                   "dd10_onset_within_120d": str(g2.index[fut[0]])[:10]
                   if fut else "",
                   "days_to_onset": (fut[0] - s) if fut else np.nan,
                   "status": "CENSORED" if (truncated and not fut) else
                   ("confirmed" if fut else "false_alert")})
    pd.DataFrame(fa).to_csv("FALSE_ALERT_AUDIT.csv", index=False)

    # --- A/B/C with proper calibration & embargo ---
    horizon = 60
    y_full = (g2.fwd_mdd60 <= -0.10).astype(float)
    y_full[g2.index > g2.index[-horizon]] = np.nan  # censor right edge
    volp = g2.vol60.expanding(min_periods=252).apply(
        lambda s: (s <= s.iloc[-1]).mean() * 100, raw=False)
    r20 = g2.ret_idx.rolling(20).sum()
    warnA = ((r20 <= -0.03) | (volp >= 80)).values
    warnB = (g2.WP >= 70).values
    warnC = warnA | warnB
    X = np.c_[g2.WP.fillna(0).values, volp.fillna(50).values,
              r20.fillna(0).values]
    # embargo: train features end 60d before valid start (label can't cross)
    vstart = g2.index.searchsorted(pd.Timestamp("2024-01-01"))
    tr_end = vstart - horizon
    tr_m = np.zeros(len(g2), bool); tr_m[:tr_end] = True
    tr_m &= ~np.isnan(y_full.values) & ~np.isnan(g2.WP.values)
    va_m = (g2.index >= "2024-01-01") & (g2.index < "2026-01-01")
    to_m = g2.index >= "2026-01-01"
    valid = ~np.isnan(y_full.values) & ~np.isnan(g2.WP.values)

    wA, muA, sdA = logistic_fit(X[tr_m][:, [1, 2]], y_full[tr_m])
    wB, muB, sdB = logistic_fit(X[tr_m][:, [0]], y_full[tr_m])
    wC, muC, sdC = logistic_fit(X[tr_m], y_full[tr_m])
    pA = logistic_pred(wA, muA, sdA, X[:, [1, 2]])
    pB = logistic_pred(wB, muB, sdB, X[:, [0]])
    pC = logistic_pred(wC, muC, sdC, X)

    iv = []
    warns = {"A_price": warnA, "B_flow": warnB, "C_AB": warnC}
    probs = {"A_price": pA, "B_flow": pB, "C_AB": pC}
    for nm in warns:
        for seg, sm in [("valid_24_25", va_m), ("touched_26", to_m)]:
            sel = sm & valid
            wv, yv, pv = warns[nm][sel], y_full[sel], probs[nm][sel]
            tp = int(((wv == 1) & (yv == 1)).sum())
            fp_ = int(((wv == 1) & (yv == 0)).sum())
            fn = int(((wv == 0) & (yv == 1)).sum())
            # coverage vs realized onsets in segment
            ons = [o["i"] for o in realized_onsets(g2, -0.10)[0]
                   if sel[o["i"]]]
            starts = [c[0] for c in clusters(list(np.flatnonzero(
                (warns[nm] & sm))), gap=10)]
            hit = sum(1 for o in ons
                      if any(o - 60 <= s <= o for s in starts))
            iv.append({"model": nm, "segment": seg, "n": int(sel.sum()),
                       "n_pos": int(yv.sum()), "n_censored_excluded":
                       int((sm & ~valid).sum()),
                       "precision": round(tp / max(1, tp + fp_), 3),
                       "recall": round(tp / max(1, tp + fn), 3),
                       "fpr": round(fp_ / max(1, (yv == 0).sum()), 3),
                       "event_coverage": round(hit / max(1, len(ons)), 3),
                       "n_events": len(ons),
                       "ap": round(pr_ap(yv, pv), 3),
                       "brier": round(float(np.mean((pv - yv) ** 2)), 4)})
    pd.DataFrame(iv).to_csv("INCREMENTAL_VALUE_VS_PRICE.csv", index=False)
    print(pd.DataFrame(iv).to_string(index=False))

    # --- DIFF table r21 vs r211 ---
    old = {}
    for f in ["INCREMENTAL_VALUE_VS_PRICE", "FALSE_ALERT_AUDIT",
              "ALERT_LEAD_TIME", "FORWARD_RISK_BY_STATE"]:
        old[f] = pd.read_csv(f"r21_baseline/{f}.csv")
    o_iv = old["INCREMENTAL_VALUE_VS_PRICE"]
    n_iv = pd.DataFrame(iv)
    drows = [{"metric": "dd10_event_coverage",
              "r21": 0.10, "r211": cov["dd10"]["coverage"]},
             {"metric": "dd15_event_coverage",
              "r21": 0.0, "r211": cov["dd15"]["coverage"]},
             {"metric": "dd10_events_n", "r21": len(
                 pd.read_csv("r21_baseline/ALERT_LEAD_TIME.csv").query(
                     "event=='dd10'")), "r211": cov["dd10"]["n_events"]},
             {"metric": "warn_cluster_n", "r21": len(
                 old["FALSE_ALERT_AUDIT"]),
              "r211": len(fa)},
             {"metric": "false_alert_rate",
              "r21": round(old["FALSE_ALERT_AUDIT"].false_alert.mean(), 3),
              "r211": round((pd.DataFrame(fa).status == "false_alert").mean()
                            / max(1e-9, (pd.DataFrame(fa).status != "CENSORED").mean()), 3)
              if True else None},
             {"metric": "state_days_changed", "r21": 0, "r211": diff_days}]
    for nm in warns:
        ro = o_iv[o_iv.model == nm].iloc[0]
        rn = n_iv[(n_iv.model == nm) & (n_iv.segment == "valid_24_25")].iloc[0]
        for m in ["precision", "recall", "ap", "brier"]:
            drows.append({"metric": f"{nm}.{m}(valid)", "r21": ro.get(m),
                          "r211": rn[m]})
    pd.DataFrame(drows).to_csv("DIFF_R21_VS_R211.csv", index=False)
    print("done")


if __name__ == "__main__":
    main()
