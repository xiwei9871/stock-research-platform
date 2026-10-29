"""M2.1 audit computations: G1 union-find episodes, G2 joint condition stats,
G3 G/H corrected evaluation, G5 market state snapshot."""
import sys
sys.path.insert(0, "../market_risk_m1")
sys.path.insert(0, "../market_risk_m2")
import numpy as np
import pandas as pd
import build_m1
build_m1.D = "../market_risk_m1/data"
from build_m1 import (load_all, features, fwd_labels, logit_fit, logit_pred,
                      ap)
from build_m2 import px_full, episodes_table, mcclellan

OBJS = ["sse", "szse", "cyb", "alla"]


# ---------- G1: union-find systemic merge ----------
def union_find_merge(ep):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    e = ep.reset_index(drop=True)
    for i in range(len(e)):
        for j in range(i + 1, len(e)):
            a, b = e.iloc[i], e.iloc[j]
            if a.obj != b.obj and a.start <= b.end and b.start <= a.end:
                union(i, j)
    e["sys_id_v2"] = [f"U{find(i):02d}" for i in range(len(e))]
    return e


def g1():
    px = px_full()
    ep = episodes_table(px)  # has greedy sys_id
    e2 = union_find_merge(ep)
    old_map = ep.set_index(["obj", "cycle_id"])["sys_id"]
    e2["old_sys_id"] = [old_map.get((r.obj, r.cycle_id)) for _, r in e2.iterrows()]
    e2.to_csv("SYSTEMIC_EPISODES_CORRECTED.csv", index=False)
    grp = e2.groupby("sys_id_v2").agg(
        objs=("obj", lambda s: "+".join(sorted(set(s)))),
        start=("start", "min"), end=("end", "max"),
        max_dd=("max_dd", "min"), n_idx=("obj", "size"))
    diff = e2.groupby("sys_id_v2").old_sys_id.nunique()
    merged_diff = diff[diff > 1]
    changed = e2[e2.old_sys_id != e2.sys_id_v2].copy()
    changed.to_csv("SYSTEMIC_EPISODE_DIFF.csv", index=False)
    print("G1: greedy sys:", ep.sys_id.nunique(),
          "| union-find:", e2.sys_id_v2.nunique(),
          "| union groups spanning >1 old id:", len(merged_diff))
    # key windows audit
    for yr in [2015, 2018, 2020, 2022, 2024, 2026]:
        w = e2[(e2.start.dt.year == yr) | (e2.trough.dt.year == yr)]
        print(" ", yr, w.groupby("sys_id_v2").size().to_dict())
    return px, e2


# ---------- G2: joint condition corrected ----------
def g2(F, e2):
    lv_med = F.lowvol20[F.index <= "2023-12-31"].median()
    joint = (F.lowvol20 > lv_med) & (F.pct_ma60_d20 < 0)
    # A: event-level — alla episodes tier=full (2020+)
    eps = e2[(e2.obj == "alla") & (e2.tier == "full")].sort_values("start")
    rows, triggers = [], []
    for _, c in eps.iterrows():
        s = c.start
        w60 = joint.loc[:s].iloc[-60:]
        first = w60[w60].index[0] if w60.any() else None
        rows.append({"cycle": c.cycle_id, "onset": str(s)[:10],
            "triggered": int(w60.any()),
            "first_trigger": str(first)[:10] if first is not None else None,
            "n_days": int(w60.sum()),
            "lead_td": int((joint.loc[:s] < True).sum() - 0) if False else
                       (len(joint.loc[first:s]) if first is not None else 0),
            "in_20d": int(joint.loc[:s].iloc[-20:].any()),
            "in_10d": int(joint.loc[:s].iloc[-10:].any())})
    # B: matched controls — same-length 60d windows from non-event days
    # sample every 120th day ending with dd120>-5% and no episode within next 60d
    starts = set(eps.start)
    endset = set(eps.end)
    days = F.index
    ctr = []
    for i in range(120, len(days) - 90, 37):
        t = days[i]
        if F.alla_dd120.iloc[i] > -0.05:
            fut = F.alla_dd120.iloc[i + 1:i + 61]
            if not (fut <= -0.10).any():
                w = joint.iloc[i - 59:i + 1]
                ctr.append({"end": str(t)[:10], "triggered": int(w.any()),
                            "n_days": int(w.sum())})
    ctrl = pd.DataFrame(ctr)
    ev = pd.DataFrame(rows)
    ev.to_csv("JOINT_CONDITION_EVENT_LEVEL.csv", index=False)
    ctrl.to_csv("MATCHED_NORMAL_CONTROLS.csv", index=False)
    # C: daily-level rate in 60d pre-onset vs other dd120>-5% days
    premask = np.zeros(len(F), bool)
    for _, c in eps.iterrows():
        loc = F.index.get_loc(c.start)
        premask[max(0, loc - 59):loc + 1] = True
    daily = pd.DataFrame({"grp": ["pre_onset", "other_pre"],
        "rate": [joint[premask].mean(),
                 joint[~premask & (F.alla_dd120 > -0.05).values].mean()],
        "n": [int(premask.sum()),
              int((~premask & (F.alla_dd120 > -0.05).values).sum())]})
    daily["rate"] = daily.rate.round(3)
    daily.to_csv("JOINT_CONDITION_DAILY_LEVEL.csv", index=False)
    print("G2: event-level", ev.triggered.mean().round(2),
          f"({ev.triggered.sum()}/{len(ev)})",
          "| ctrl:", ctrl.triggered.mean().round(2), f"({len(ctrl)})",
          "| daily:", daily.rate.tolist())
    return ev, ctrl, daily


# ---------- G3: G conditional + H corrected ----------
def g3(F, e2):
    p = F  # alla features mapped in M2 prepare
    from analyze_m2 import prepare, G_FEATS, H_FEATS
    F = prepare(F)
    px = px_full()
    pa = px["alla"].ffill()
    fw = fwd_labels(pa)
    emb = F.index < (pd.Timestamp("2024-01-01") - pd.Timedelta(days=90))
    decl = F.alla_dd120 <= -0.10
    yG = pd.Series(np.where(np.isnan(fw[20][1]), np.nan,
                            (fw[20][1] <= -.05).astype(float)), index=F.index)
    # G: conditional percentile = distribution over TRAIN in-decline days only
    X = F[G_FEATS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    trm = (F.index <= "2023-12-31") & emb & decl.values & ~yG.isna().values
    w, mu, sd = logit_fit(X[trm], yG[trm].values)
    pr = pd.Series(logit_pred(X, w, mu, sd), index=F.index)
    hist_decl = pr[trm]
    pct = pr.apply(lambda s: (hist_decl <= s).mean())
    rows = []
    for seg, m in [("train", (F.index <= "2023-12-31") & decl.values),
                   ("valid", (F.index >= "2024-01-01") &
                    (F.index < "2026-01-01") & decl.values),
                   ("replay", (F.index >= "2026-01-01") & decl.values)]:
        mm = m & ~yG.isna().values
        if mm.sum() < 20:
            rows.append({"seg": seg, "n": int(mm.sum()),
                         "eval": "NOT_EVALUABLE"})
            continue
        rows.append({"seg": seg, "n": int(mm.sum()),
            "pos": int(yG[mm].sum()),
            "ap": round(ap(yG[mm], pr[mm]), 3),
            "alert_share": round((pct[mm] >= .8).mean(), 3),
            "eval": "OK" if yG[mm].nunique() > 1 else "NOT_EVALUABLE"})
    gdf = pd.DataFrame(rows)
    gdf.to_csv("PRESSURE_G_CORRECTED_EVALUATION.csv", index=False)
    print("G3 G:", gdf.to_string(index=False))
    # H: corrected labels — recover confirmed = dd120 exits >-5% AND stays
    # out of <=-10% for CONF=40 trading days after first recovery
    CONF = 40
    dd = F.alla_dd120.values
    yH = pd.Series(np.nan, index=F.index)
    for i in range(len(dd) - 100):
        if dd[i] <= -0.10:
            fut = dd[i + 1:i + 61]
            rec = np.flatnonzero(fut > -0.05)
            if not len(rec):
                yH.iloc[i] = 0.0  # no recovery in 60d
            else:
                r0 = i + 1 + rec[0]
                tail = dd[r0 + 1:r0 + 1 + CONF]
                if len(tail) < CONF:
                    yH.iloc[i] = np.nan  # censored
                else:
                    yH.iloc[i] = float(not (tail <= -0.10).any())
    hstat = yH.value_counts(dropna=False)
    print("H labels:", hstat.to_dict())
    Xh = F[H_FEATS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    hrows = []
    for seg, m in [("train", (F.index <= "2023-12-31") & decl.values),
                   ("valid", (F.index >= "2024-01-01") &
                    (F.index < "2026-01-01") & decl.values),
                   ("replay", (F.index >= "2026-01-01") & decl.values)]:
        mm = m & ~yH.isna().values
        pos = int(yH[mm].sum()) if mm.sum() else 0
        ev_ok = mm.sum() >= 20 and 0 < pos < mm.sum()
        if mm.sum() >= 20 and ev_ok:
            tr = trm & ~yH.isna().values
            wh, mh, sh = logit_fit(Xh[tr], yH[tr].values)
            prh = logit_pred(Xh, wh, mh, sh)
            hrows.append({"seg": seg, "n": int(mm.sum()), "pos": pos,
                "ap": round(ap(yH[mm], prh[mm]), 3), "eval": "OK"})
        else:
            hrows.append({"seg": seg, "n": int(mm.sum()), "pos": pos,
                          "eval": "NOT_EVALUABLE"})
    hdf = pd.DataFrame(hrows)
    hdf.to_csv("REPAIR_H_EVALUATION.csv", index=False)
    pd.DataFrame({"date": F.index, "dd120": F.alla_dd120.values,
                  "yH_corrected": yH.values}).to_csv(
        "REPAIR_H_CORRECTED_LABELS.csv", index=False)
    print("G3 H:", hdf.to_string(index=False))
    return F


# ---------- G5: market state 2026-10-28 ----------
def g5(F):
    import json
    t = F.index[-1]
    i = len(F) - 1
    emo, br, px = load_all()
    st = {}
    for k in ["sse", "szse", "cyb", "alla"]:
        p = px[k].ffill()
        st[k] = {"close": round(float(p.iloc[-1]), 2),
            "ret20": round(float(p.iloc[-1] / p.iloc[-21] - 1), 4),
            "ret60": round(float(p.iloc[-1] / p.iloc[-61] - 1), 4),
            "dd120": round(float(F[f"{k}_dd120"].iloc[i]), 4),
            "in_major_decline": bool(F[f"{k}_dd120"].iloc[i] <= -0.10)}
    e = emo.reindex(F.index)
    mk = {"emotion_score": float(e.emotion_score.iloc[-1]),
          "up_share": round(float(e.up_count.iloc[-1] /
                                e.traded_count.iloc[-1]), 3),
          "pct_above_ma60": round(float(F.pct_ma60.iloc[i]), 3),
          "pct_ma60_d20": round(float(F.pct_ma60_d20.iloc[i]), 3),
          "lowvol_streak": int(F.lowvol_streak.iloc[i]),
          "amt_ratio_5_20": round(float(F.amt_ratio_5_20.iloc[i]), 3),
          "amt_ratio_20_60": round(float(F.amt_ratio_20_60.iloc[i]), 3),
          "g1_depth": round(float(F.g1_depth.iloc[i]), 3)
          if not np.isnan(F.g1_depth.iloc[i]) else None,
          "g1_vel20": round(float(F.g1_vel20.iloc[i]), 3),
          "mcc_osc": round(float(F.mcc_osc.iloc[i]), 1)}
    out = {"as_of": str(t)[:10], "data_cutoff": "2026-10-28",
           "indices": st, "market": mk,
           "risk_labels": {"advance_warning": "NOT_EVALUATED",
                           "probability_calibration": "NOT_CALIBRATED",
                           "regime": "DECLINE (dd120<=-10% all objs)"}}
    json.dump(out, open("MARKET_STATE_2026_10_28.json", "w"),
              ensure_ascii=False, indent=1)
    return out


def main():
    px, e2 = g1()
    emo, br, _ = load_all()
    F = features(emo, br, px)
    F = F.join(mcclellan(emo.reindex(F.index)))
    ev, ctrl, daily = g2(F, e2)
    F = g3(F, e2)
    st = g5(F)
    import json
    print(json.dumps(st["indices"], indent=0))


if __name__ == "__main__":
    main()
