"""M1.1 diagnostics: ETF failure root cause, corrected event audit,
persistence mechanisms on frozen models, controlled ETF ablation."""
import sys
sys.path.insert(0, "../market_risk_m1")
import numpy as np
import pandas as pd
import build_m1
build_m1.D = "../market_risk_m1/data"
from build_m1 import (load_all, features, fwd_labels, cycles_from_dd,
                      logit_fit, logit_pred, ap,
                      A_COLS, B_EXTRA, C_EXTRA, D_EXTRA)

KEYD = ["2026-07-01", "2026-07-07", "2026-07-13", "2026-07-17",
        "2026-08-31", "2026-09-30", "2026-10-27"]
OBJS = ["sse", "szse", "cyb", "alla"]
TR_END = "2023-12-31"


def seg_of(t):
    return ("train" if t <= pd.Timestamp("2023-12-31") else
            "valid" if t < pd.Timestamp("2026-01-01") else "replay")


def p1_diagnostics(F):
    cols = C_EXTRA + D_EXTRA
    rows = []
    for c in cols:
        s = F[c]
        for seg in ["train", "valid", "replay"]:
            v = s[[seg_of(t) == seg for t in F.index]]
            rows.append({"feat": c, "seg": seg, "n": len(v),
                "zero_pct": round((v == 0).mean(), 3),
                "nan_pct": round(v.isna().mean(), 3),
                "mean": round(v.mean(), 4), "p95": round(v.quantile(.95), 4),
                "max": round(v.max(), 4)})
        corr = F[cols].corr()[c].drop(c).abs().max()
        rows[-1]["max_abs_corr"] = round(corr, 3)
    out = pd.DataFrame(rows)
    out.to_csv("ETF_FEATURE_DIAGNOSTICS.csv", index=False)
    return out


def coefs_and_contrib(F, y, trm):
    cols = A_COLS("alla") + B_EXTRA + C_EXTRA + D_EXTRA
    X = F[cols].replace([np.inf, -np.inf], np.nan).fillna(0).values
    w, mu, sd = logit_fit(X[trm], y[trm].values)
    coef = pd.DataFrame({"feat": cols, "w": w[1:],
                         "direction": np.sign(w[1:])})
    contrib_rows = []
    for kd in KEYD:
        t = pd.Timestamp(kd)
        if t not in F.index:
            continue
        i = F.index.get_loc(t)
        xv = (X[i] - mu) / sd
        for j, c in enumerate(cols):
            contrib_rows.append({"date": kd, "feat": c,
                "x_raw": X[i][j], "z": round(xv[j], 2),
                "contrib": round(w[1 + j] * xv[j], 3)})
    coef.to_csv("ETF_MODEL_COEFS.csv", index=False)
    pd.DataFrame(contrib_rows).to_csv("ETF_MODEL_CONTRIBUTIONS.csv",
                                      index=False)
    # B vs C prediction gap on key dates
    colsB = A_COLS("alla") + B_EXTRA
    colsC = colsB + C_EXTRA
    XB = F[colsB].fillna(0).values
    XC = F[colsC].fillna(0).values
    wB, mB, sB = logit_fit(XB[trm], y[trm].values)
    wC, mC, sC = logit_fit(XC[trm], y[trm].values)
    prB, prC = logit_pred(XB, wB, mB, sB), logit_pred(XC, wC, mC, sC)
    rows = []
    for kd in KEYD:
        t = pd.Timestamp(kd)
        if t not in F.index:
            continue
        i = F.index.get_loc(t)
        rows.append({"date": kd, "prB": round(prB[i], 4),
                     "prC": round(prC[i], 4),
                     "gap": round(prC[i] - prB[i], 4)})
    pd.DataFrame(rows).to_csv("B_VS_C_KEYDATES.csv", index=False)
    return pd.DataFrame(rows)


def episodes(sn, obj, model):
    s = sn[(sn.obj == obj) & (sn.model == model)].sort_values("date")
    a = s.state.isin(["WATCH", "ELEVATED", "HIGH"]).values
    eps, st = [], None
    for i, v in enumerate(a):
        if v and st is None:
            st = i
        if st is not None and (not v or i == len(a) - 1):
            e = i - 1 if not v else i
            seg = s.iloc[st:e + 1]
            eps.append({"obj": obj, "model": model,
                "start": str(seg.date.iloc[0])[:10],
                "end": str(seg.date.iloc[-1])[:10],
                "days": len(seg),
                "peak": seg.state.value_counts().index[-1] if len(seg) else None})
            st = None
    return eps


def corrected_audit(sn, cy):
    """Events before replay window: NOT_EVALUATED; 2026: dual coverage."""
    rows = []
    for _, c in cy.iterrows():
        onset = c.first_dd10
        for m in ["0", "A", "B", "C", "D"]:
            if onset < pd.Timestamp("2026-07-01"):
                rows.append({"obj": c.obj, "cycle": c.cycle_id,
                    "onset": str(onset)[:10], "model": m,
                    "eval_status": "NOT_EVALUATED"})
                continue
            s = sn[(sn.obj == c.obj) & (sn.model == m)
                   & (sn.date <= onset)].sort_values("date")
            st = s.state.iloc[-1] if len(s) else "NONE"
            r = {"obj": c.obj, "cycle": c.cycle_id,
                 "onset": str(onset)[:10], "model": m,
                 "eval_status": "EVALUATED", "onset_state": st}
            for w in [5, 10, 20, 40]:
                prior = s.tail(w + 1).iloc[:-1]
                r[f"prior{w}d"] = int(prior.state.isin(
                    ["WATCH", "ELEVATED", "HIGH"]).any()) if len(prior) else 0
            rows.append(r)
    return pd.DataFrame(rows)


def sm_variants(pct):
    """Persistence mechanisms on a score-pct series -> state labels."""
    pct = pct.fillna(0).values
    n = len(pct)
    out = {}
    # raw
    out["raw"] = np.where(pct >= .9, "HIGH", np.where(pct >= .8, "ELEVATED",
                 np.where(pct >= .6, "WATCH", "NORMAL")))
    # hysteresis: enter>=.8 exit<.55
    st = np.zeros(n, int)
    cur = 0
    for i in range(n):
        if cur == 0 and pct[i] >= .8:
            cur = 1
        elif cur == 1 and pct[i] < .55:
            cur = 0
        st[i] = cur
    out["hysteresis"] = np.where(st, "WATCH", "NORMAL")
    # confirm2+release5: enter 2d>=.8, exit after 5d<.8
    cur, cin, cout = 0, 0, 0
    st = np.zeros(n, int)
    for i in range(n):
        if cur == 0:
            cin = cin + 1 if pct[i] >= .8 else 0
            if cin >= 2:
                cur = 1
        else:
            cout = cout + 1 if pct[i] < .8 else 0
            if pct[i] >= .8:
                cout = 0
            if cout >= 5:
                cur = 0; cin = 0
        st[i] = cur
    out["confirm2_rel5"] = np.where(st, "WATCH", "NORMAL")
    # memory10: warn if any of past 10d >=.9
    m = pd.Series(pct >= .9).rolling(10, min_periods=1).max().values
    out["memory10"] = np.where(m, "WATCH", "NORMAL")
    return out


def eval_sm(states, y_events_dates, idx):
    """Coverage of event dates + alert-day share."""
    s = pd.Series(states, index=idx)
    a = s != "NORMAL"
    cov = {}
    for d in y_events_dates:
        d = pd.Timestamp(d)
        w = s[(s.index < d) & (s.index >= d - pd.Timedelta(days=60))]
        cov[str(d)[:10]] = {
            "onset_active": int(s.asof(d) != "NORMAL") if len(s) else 0,
            "prior_any": int((w != "NORMAL").any())}
    eps = episodes(pd.DataFrame({"obj": "x", "model": "x", "date": idx,
                                 "state": states}), "x", "x")
    return {"alert_days": int(a.sum()), "share": round(a.mean(), 3),
            "n_eps": len(eps), "coverage": cov}


def main():
    emo, br, px = load_all()
    F = features(emo, br, px)
    print("P1 diagnostics...")
    d1 = p1_diagnostics(F)
    print(d1[d1.seg == "replay"].to_string(index=False))
    # labels alla for diagnosis
    p = px["alla"].ffill()
    fw = fwd_labels(p)
    y = pd.Series(np.where(np.isnan(fw[60][2]), np.nan,
                           (fw[60][2] <= -.10).astype(float)), index=F.index)
    emb = F.index < (pd.Timestamp("2024-01-01") - pd.Timedelta(days=90))
    trm = (F.index <= TR_END) & ~y.isna().values & emb
    print("\nP1 contributions...")
    print(coefs_and_contrib(F, y, trm).to_string(index=False))
    # --- Phase 2 corrected audit ---
    sn = pd.read_csv("../market_risk_m1/REPLAY_DAILY_SNAPSHOTS.csv",
                     parse_dates=["date"])
    cy = pd.read_csv("../market_risk_m1/2026_INDEPENDENT_RISK_CYCLES.csv",
                     parse_dates=["first_dd10", "trough"])
    ca = corrected_audit(sn, cy)
    ca.to_csv("CORRECTED_EVENT_AUDIT.csv", index=False)
    eps = []
    for o in OBJS:
        for m in ["0", "A", "B", "C", "D"]:
            eps += episodes(sn, o, m)
    pd.DataFrame(eps).to_csv("ALERT_EPISODE_LEDGER.csv", index=False)
    print(ca[ca.eval_status == "EVALUATED"].to_string(index=False))
    # --- Phase 3 persistence on Model B score (alla + sse + cyb + szse) ---
    sm_rows = []
    for obj in OBJS:
        yk = pd.Series(np.where(np.isnan(fwd_labels(px[obj].ffill())[60][2]),
                                np.nan, (fwd_labels(px[obj].ffill())[60][2]
                                         <= -.10).astype(float)),
                       index=F.index)
        trmk = (F.index <= TR_END) & ~yk.isna().values & emb
        colsB = A_COLS(obj) + B_EXTRA
        XB = F[colsB].fillna(0).values
        w, mu, sd = logit_fit(XB[trmk], yk[trmk].values)
        pr = pd.Series(logit_pred(XB, w, mu, sd), index=F.index)
        hist = pr[pr.index <= "2023-12-31"]
        pct = pr.apply(lambda s: (hist <= s).mean())
        ev26 = cy[(cy.obj == obj) & (cy.first_dd10 >= "2026-07-01")
                  ].first_dd10.tolist()
        evh = cy[(cy.obj == obj) & (cy.first_dd10 < "2026-01-01")
                 ].first_dd10.tolist()
        for vn, stt in sm_variants(pct).items():
            v = eval_sm(stt, ev26, pct.index)
            h = eval_sm(stt, evh, pct.index)
            sm_rows.append({"obj": obj, "mech": vn,
                "alert_days_2426": v["alert_days"],
                "share": v["share"], "n_eps": v["n_eps"],
                "cov26": str(v["coverage"]),
                "hist_onset_cov": sum(c["onset_active"]
                                      for c in h["coverage"].values()),
                "hist_prior_cov": sum(c["prior_any"]
                                      for c in h["coverage"].values()),
                "hist_n_ev": len(evh)})
    smdf = pd.DataFrame(sm_rows)
    smdf.to_csv("STATE_MACHINE_COMPARISON.csv", index=False)
    print(smdf.to_string(index=False))
    # --- Phase 4 ablation (alla label, B0..B6) ---
    groups = {
        "B0_no_etf": A_COLS("alla") + B_EXTRA,
        "B1_g1_all": A_COLS("alla") + B_EXTRA +
            ["g1_depth", "g1_ddur", "g1_vel20", "g1_breadth", "g1_reacc"],
        "B2_broad": A_COLS("alla") + B_EXTRA +
            ["g2_depth", "g2_vel20", "g3_depth"],
        "B3_depth": A_COLS("alla") + B_EXTRA + ["g1_depth"],
        "B4_dur_vel": A_COLS("alla") + B_EXTRA + ["g1_ddur", "g1_vel20"],
        "B5_inflow": A_COLS("alla") + B_EXTRA + ["g1_reacc", "g1_vel20"],
        "B6_interact": A_COLS("alla") + B_EXTRA +
            ["x_etf_breadth_bad", "x_etf_trend_dn", "x_reacc_breadth"]}
    ab_rows = []
    for mn, cols in groups.items():
        X = F[cols].fillna(0).values
        w, mu, sd = logit_fit(X[trm], y[trm].values)
        pr = logit_pred(X, w, mu, sd)
        for seg, msk in [("valid", (F.index >= "2024-01-01") &
                          (F.index < "2026-01-01") & ~y.isna()),
                         ("replay", (F.index >= "2026-01-01") & ~y.isna())]:
            if msk.sum() < 30:
                continue
            ab_rows.append({"model": mn, "seg": seg, "n": int(msk.sum()),
                "ap": round(ap(y[msk], pr[msk]), 3),
                "brier": round(float(np.mean((pr[msk] - y[msk].values) ** 2)),
                               4)})
    ab = pd.DataFrame(ab_rows)
    ab.to_csv("ETF_ABLATION_RESULTS.csv", index=False)
    print(ab.to_string(index=False))
    print("done")


if __name__ == "__main__":
    main()
