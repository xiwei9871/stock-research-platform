"""M2 Phase4-6: event study, models E/F/G/H, frozen 2026 stress test."""
import sys
sys.path.insert(0, "../market_risk_m1")
import numpy as np
import pandas as pd
import build_m1
build_m1.D = "../market_risk_m1/data"
from build_m1 import (load_all, features, fwd_labels, cycles_from_dd,
                      logit_fit, logit_pred, ap, A_COLS)
from build_m2 import px_full, episodes_table

E_FEATS = ["ret60", "dd120", "trend", "vol60", "dvol60",
           "pct_ma60_20", "pct_ma60_d20", "pct_hi20",
           "lowvol20", "lowvol_streak", "amt_ratio_20_60", "amt_ratio_5_20",
           "emotion20", "emotion_down_streak", "breadth_bad_streak",
           "dn_share20", "up_share20", "limit_up20", "broken20",
           "mcc_osc", "mcc_sum_d20"]
F_ETF = ["g1_depth", "g1_ddur", "g1_vel20"]
G_FEATS = ["ret20", "dd120", "dd_slope20", "dn_share20", "strong_dn20",
           "pct_ma60_d20", "amt_ratio_5_20", "limit_dn20", "vol60",
           "mcc_osc", "g1_vel20", "g1_reacc"]
H_FEATS = ["pct_ma60_d20", "amt_ratio_5_20", "ret20", "emotion20",
           "g1_reacc", "g1_vel20", "mcc_osc", "limit_up20"]


def prepare(F):
    F = F.copy()
    for k in ["sse", "szse", "cyb", "alla"]:
        p = F[k + "_ret20"].index  # index only
    F["dd_slope20"] = F["alla_dd120"].diff(20)
    F["mcc_sum_d20"] = F["mcc_sum"].diff(20)
    F["ret60"] = F["alla_ret60"]
    F["ret20"] = F["alla_ret20"]
    F["dd120"] = F["alla_dd120"]
    F["trend"] = F["alla_trend"]
    F["vol60"] = F["alla_vol60"]
    F["dvol60"] = F["alla_dvol60"]
    return F


def domain_masks(F):
    pre = F["alla_dd120"] > -0.05
    decl = F["alla_dd120"] <= -0.10
    return pre, decl


def run_model(X, y, trm):
    w, mu, sd = logit_fit(X[trm], y[trm].values)
    return logit_pred(X, w, mu, sd)


def eval_segs(y, pr, F, name, domain):
    rows = []
    for seg, msk in [("train", F.index <= "2023-12-31"),
                     ("valid", (F.index >= "2024-01-01") &
                      (F.index < "2026-01-01")),
                     ("replay26", F.index >= "2026-01-01")]:
        m = np.asarray(msk) & domain.values & ~y.isna().values
        if m.sum() < 30 or y[m].sum() < 3:
            rows.append({"model": name, "seg": seg, "n": int(m.sum()),
                         "pos": int(y[m].sum() if m.sum() else 0),
                         "ap": np.nan, "brier": np.nan})
            continue
        rows.append({"model": name, "seg": seg, "n": int(m.sum()),
            "pos": int(y[m].sum()),
            "ap": round(ap(y[m], pr[m]), 3),
            "brier": round(float(np.mean((pr[m] - y[m].values) ** 2)), 4)})
    return rows


def main():
    px = px_full()
    ep = episodes_table(px)
    emo, br, _ = load_all()
    F = features(emo, br, px)
    import sys as s
    s.path.insert(0, ".")
    from build_m2 import mcclellan
    F = F.join(mcclellan(emo.reindex(F.index)))
    F = prepare(F)
    p = px["alla"].ffill()
    fw = fwd_labels(p)
    emb = F.index < (pd.Timestamp("2024-01-01") - pd.Timedelta(days=90))
    pre, decl = domain_masks(F)
    # --- labels ---
    yA = pd.Series(np.where(np.isnan(fw[60][2]), np.nan,
                            (fw[60][2] <= -.10).astype(float)), index=F.index)
    yG = pd.Series(np.where(np.isnan(fw[20][1]), np.nan,
                            (fw[20][1] <= -.05).astype(float)), index=F.index)
    dd120 = p / p.rolling(120, min_periods=30).max() - 1
    rec = pd.Series(np.nan, index=F.index)
    dd = dd120.values
    for i in range(len(dd) - 60):
        fut = dd[i + 1:i + 61]
        rec.iloc[i] = float((fut > -0.05).any())
    yH = rec
    trm = (F.index <= "2023-12-31") & emb
    results = []
    # --- Module A: E, F ---
    XE = F[E_FEATS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    prE = run_model(XE, yA, trm & ~yA.isna().values)
    F["prE"] = prE
    results += eval_segs(yA, prE, F, "E_fragility", pre)
    XF_ = F[E_FEATS + F_ETF].replace([np.inf, -np.inf], np.nan)
    # OOD clip at train p1-p99
    for c in F_ETF:
        lo, hi = XF_[c][trm].quantile([.01, .99])
        XF_[c] = XF_[c].clip(lo, hi)
    prF = run_model(XF_.fillna(0).values, yA, trm & ~yA.isna().values)
    F["prF"] = prF
    results += eval_segs(yA, prF, F, "F_etf", pre)
    # --- Module B: G ---
    XG = F[G_FEATS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    prG = run_model(XG, yG, trm & ~yG.isna().values)
    F["prG"] = prG
    results += eval_segs(yG, prG, F, "G_pressure", decl)
    # --- Module C: H ---
    XH = F[H_FEATS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    prH = run_model(XH, yH, trm & ~yH.isna().values)
    F["prH"] = prH
    results += eval_segs(yH, prH, F, "H_repair", decl)
    # --- baselines for comparison on module A domain ---
    from build_m1 import B_EXTRA
    XB = F[A_COLS("alla") + B_EXTRA].fillna(0).values
    prB = run_model(XB, yA, trm & ~yA.isna().values)
    results += eval_segs(yA, prB, F, "M1_B", pre)
    rdf = pd.DataFrame(results)
    rdf.to_csv("M2_MODEL_RESULTS.csv", index=False)
    print(rdf.to_string(index=False))
    # ---------- Phase 4 event study (2020+ systemic episodes, alla) ----------
    es = []
    onsets = ep[(ep.obj == "alla") & (ep.tier == "full")].start.tolist()
    keys = ["pct_ma60_20", "emotion20", "amt_ratio_20_60", "g1_depth",
            "lowvol20", "mcc_osc", "breadth_bad_streak"]
    for lag in [-60, -40, -20, -10, -5, 0]:
        row = {"lag": lag}
        for k in keys:
            vals = []
            for o in onsets:
                t = F.index.get_loc(o) + lag
                if 0 <= t < len(F):
                    vals.append(F[k].iloc[t])
            row[k] = round(float(np.nanmean(vals)), 3)
        es.append(row)
    esdf = pd.DataFrame(es)
    ctrl = F[pre & (F.index <= "2025-12-31")][keys].mean().round(3)
    esdf["normal_baseline"] = esdf.apply(
        lambda r: "", axis=1)
    for k in keys:
        esdf[k + "_baseline"] = round(ctrl[k], 3)
    esdf.to_csv("EVENT_ALIGNED_INDICATORS.csv", index=False)
    print(esdf[["lag"] + keys].to_string(index=False))
    # conditional rates: low-vol & breadth-deterioration co-occurrence
    lv_med = F.lowvol20[F.index <= "2023-12-31"].median()
    cond_rows = []
    for lag in [-60, -20, -5]:
        hits, tot = 0, 0
        for o in onsets:
            t = F.index.get_loc(o) + lag
            if 0 <= t < len(F):
                tot += 1
                if (F.lowvol20.iloc[t] > lv_med) & \
                   (F.pct_ma60_d20.iloc[t] < 0):
                    hits += 1
        nb = ((F.lowvol20 > lv_med) & (F.pct_ma60_d20 < 0) & pre).mean()
        cond_rows.append({"lag": lag, "joint_rate": round(hits / max(tot, 1), 2),
                          "n": tot, "baseline_rate": round(nb, 3)})
    pd.DataFrame(cond_rows).to_csv("NORMAL_PERIOD_CONTROLS.csv", index=False)
    # ---------- Phase 6: frozen 2026 daily states ----------
    hist = F.prE[F.index <= "2025-12-31"]
    rows = []
    for t in F.index[F.index >= "2026-05-01"]:
        i = F.index.get_loc(t)
        pctE = (hist <= prE[i]).mean()
        stE = "NORMAL" if pctE < .8 else ("WATCH" if pctE < .9 else "ELEVATED")
        histG = F.prG[F.index <= "2025-12-31"]
        pctG = (histG <= prG[i]).mean()
        stG = "NORMAL" if pctG < .8 else ("WATCH" if pctG < .9 else "ELEVATED")
        histH = F.prH[F.index <= "2025-12-31"]
        pctH = (histH <= prH[i]).mean()
        stH = ("REPAIR" if pctH > .8 else "WEAK" if pctH > .5 else
               "STILL_DECLINING")
        rows.append({"date": str(t)[:10],
            "dd120": round(float(F.alla_dd120.iloc[i]), 3),
            "regime": "PRE" if F.alla_dd120.iloc[i] > -.05 else
                      ("DECLINE" if F.alla_dd120.iloc[i] <= -.10 else "MILD"),
            "E_pct": round(pctE, 3), "E_state": stE,
            "F_pct": round((F.prF[F.index <= "2025-12-31"] <=
                            prF[i]).mean(), 3),
            "G_pct": round(pctG, 3), "G_state": stG,
            "H_pct": round(pctH, 3), "H_state": stH,
            "g1_depth": round(float(F.g1_depth.iloc[i])
                              if not np.isnan(F.g1_depth.iloc[i]) else 0, 3),
            "lowvol_streak": int(F.lowvol_streak.iloc[i]),
            "pct_ma60_d20": round(float(F.pct_ma60_d20.iloc[i]), 3)})
    rep = pd.DataFrame(rows)
    rep.to_csv("M2_2026_DAILY_STATES.csv", index=False)
    print(rep.head(40).to_string(index=False))


if __name__ == "__main__":
    main()
