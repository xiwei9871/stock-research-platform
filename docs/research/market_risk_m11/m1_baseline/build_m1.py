"""M1 unified pipeline: PIT features, risk events/cycles, models 0/A/B/C/D.

All features use only day-t data. Labels are future-path (audit-only, never
fed back into features). Train <=2023-12-31 with 60d embargo; valid 2024-25;
2026-07+ = touched replay.
"""
import sys
sys.path.insert(0, "../etf_flow_r31")
import numpy as np
import pandas as pd
from analyze_r31 import engine as etf_engine

D = "data"
IDXMAP = {"sse": "SSE_COMPOSITE", "szse": "SZSE_COMPONENT",
          "cyb": "CHINEXT", "hs300": "CSI_300"}
FWIN = [20, 40, 60, 120]


def load_all():
    emo = pd.read_parquet(f"{D}/emotion_daily.parquet").set_index("trade_date")
    br = pd.read_parquet(f"{D}/breadth_daily.parquet").set_index("trade_date")
    idx = pd.read_parquet(f"{D}/index_daily.parquet")
    idx["close"] = idx["close"].astype(float)
    px = idx.pivot(index="trade_date", columns="index_id", values="close")
    px = px.rename(columns={v: k for k, v in IDXMAP.items()})
    aa = pd.read_csv("../etf_flow_poc02/data/index_daily.csv", parse_dates=["date"])
    px["alla"] = aa.set_index("date")["all_a"].reindex(px.index).ffill()
    return emo, br, px.sort_index()


def fwd_labels(p: pd.Series):
    n = len(p)
    out = {}
    arr = p.values
    for w in FWIN:
        mdd, low, ret = (np.full(n, np.nan) for _ in range(3))
        for i in range(n):
            e = min(n, i + w + 1)
            if e - i <= w:
                continue
            f = arr[i + 1:e]
            ret[i] = f[-1] / arr[i] - 1
            low[i] = f.min() / arr[i] - 1
            path = np.r_[arr[i], f]
            mdd[i] = (path / np.maximum.accumulate(path)).min() - 1
        out[w] = (ret, low, mdd)
    return out


def cycles_from_dd(dd: pd.Series, enter=-0.10, exit_dd=-0.05):
    """Independent decline episodes: enter when dd<=enter, close when dd>exit.
    All crossings inside an unrecovered episode merge into one cycle."""
    cyc, cur, cid = [], None, 0
    d = dd.values
    for i, v in enumerate(d):
        if cur is None and v <= enter:
            cur = {"cycle_id": f"C{cid:02d}", "start_i": i,
                   "first_cross": dd.index[i]}
            cid += 1
        if cur is not None:
            if v > exit_dd or i == len(d) - 1:
                cur["end_i"] = i
                cur["end"] = dd.index[i]
                cur["status"] = ("OPEN" if i == len(d) - 1 and v <= exit_dd
                                 else "COMPLETED")
                cyc.append(cur)
                cur = None
    return cyc


def features(emo, br, px):
    f = pd.DataFrame(index=px.index)
    # --- price/vol per index (A) ---
    for k in ["sse", "szse", "cyb", "hs300", "alla"]:
        p = px[k].ffill()
        f[f"{k}_ret20"] = p.pct_change(20)
        f[f"{k}_ret60"] = p.pct_change(60)
        f[f"{k}_dd120"] = p / p.rolling(120, min_periods=30).max() - 1
        r = p.pct_change()
        f[f"{k}_vol60"] = r.rolling(60).std()
        f[f"{k}_dvol60"] = r.clip(upper=0).rolling(60).std()
        f[f"{k}_trend"] = p / p.rolling(60).mean() - 1
    # --- market internals (B) ---
    e = emo.reindex(f.index)
    f["n"] = e.traded_count
    f["up_share"] = e.up_count / e.traded_count
    f["up_share20"] = f.up_share.rolling(20).mean()
    f["dn_share20"] = (e.down_count / e.traded_count).rolling(20).mean()
    f["strong_dn20"] = (e.strong_down_count / e.traded_count).rolling(20).mean()
    f["limit_up20"] = e.limit_up_count.rolling(20).mean()
    f["limit_dn20"] = e.limit_down_count.rolling(20).mean()
    f["broken20"] = e.broken_limit_up_rate.rolling(20).mean()
    f["emotion"] = e.emotion_score
    f["emotion20"] = e.emotion_score.rolling(20).mean()
    f["emotion_d5"] = e.emotion_score.diff(5)
    f["emotion_down_streak"] = (
        e.emotion_score.diff() < 0).groupby(
        (e.emotion_score.diff() >= 0).cumsum()).cumsum()
    f["amt"] = e.total_amount
    f["amt_ratio_5_20"] = e.amount_ratio_5_20
    f["amt_ratio_20_60"] = (e.total_amount.rolling(20).mean() /
                          e.total_amount.rolling(60).mean())
    f["amt_pct20"] = (e.total_amount.rolling(20).mean() /
                      e.total_amount.expanding().median())
    lowvol = e.total_amount < 0.8 * e.total_amount.rolling(60).median()
    f["lowvol20"] = lowvol.rolling(20).mean()
    f["lowvol_streak"] = lowvol.groupby((~lowvol).cumsum()).cumsum()
    bb = br.reindex(f.index)
    f["pct_ma60"] = bb.pct_above_ma60
    f["pct_ma60_20"] = bb.pct_above_ma60.rolling(20).mean()
    f["pct_ma60_d20"] = bb.pct_above_ma60.diff(20)
    f["pct_hi20"] = bb.pct_at_hi20.rolling(20).mean()
    f["breadth_bad_streak"] = (
        bb.pct_above_ma60.diff() < 0).groupby(
        (bb.pct_above_ma60.diff() >= 0).cumsum()).cumsum()
    # --- ETF flows (C) via R3.1 engine ---
    for gname in ["G1_all_equity", "G2_hs300_head", "G3_other_broad"]:
        g = pd.read_parquet(f"../etf_flow_r21/data/factors_{gname}.parquet")
        g.index = pd.to_datetime(g.index)
        d2, _ = etf_engine(g)
        pre = gname.split("_")[0].lower()
        f[f"{pre}_depth"] = d2.pdepth.reindex(f.index)
        f[f"{pre}_ddur"] = d2.ddur.reindex(f.index)
        f[f"{pre}_vel20"] = d2.vel20.reindex(f.index)
        f[f"{pre}_breadth"] = d2.breadth_out.reindex(f.index)
        f[f"{pre}_reacc"] = (d2.pstate.reindex(f.index) ==
                             "REACCUMULATING").astype(float)
    # --- D: preregistered interactions ---
    f["x_etf_breadth_bad"] = f.g1_depth.fillna(0) * (-f.pct_ma60_d20).clip(0)
    f["x_etf_price_up"] = f.g1_depth.fillna(0) * f.sse_ret20.clip(0)
    f["x_lowvol_breadth"] = f.lowvol20 * (-f.pct_ma60_d20).clip(0)
    f["x_etf_trend_dn"] = f.g1_depth.fillna(0) * (-f.sse_trend).clip(0)
    f["x_reacc_breadth"] = f.g1_reacc * f.pct_ma60_d20.clip(0)
    return f


def logit_fit(Xtr, ytr, n_iter=600, lr=0.05):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    Xb = np.c_[np.ones(len(Xtr)), (Xtr - mu) / sd]
    w = np.zeros(Xb.shape[1])
    for _ in range(n_iter):
        p = 1 / (1 + np.exp(-Xb @ w))
        w -= lr * (Xb.T @ (p - ytr) / len(ytr) + 1e-3 * w)
    return w, mu, sd


def logit_pred(Xte, w, mu, sd):
    return 1 / (1 + np.exp(-np.c_[np.ones(len(Xte)), (Xte - mu) / sd] @ w))


def ap(y, s):
    o = np.argsort(-np.asarray(s))
    yv = np.asarray(y)[o]
    tp = np.cumsum(yv)
    return float((tp / np.arange(1, len(yv) + 1) * yv).sum() /
                 max(1, yv.sum()))


A_COLS = lambda k: [f"{k}_ret20", f"{k}_ret60", f"{k}_dd120",
                    f"{k}_vol60", f"{k}_dvol60", f"{k}_trend"]
B_EXTRA = ["up_share20", "dn_share20", "strong_dn20", "limit_up20",
           "limit_dn20", "broken20", "emotion", "emotion20", "amt_ratio_5_20",
           "amt_ratio_20_60", "lowvol20", "pct_ma60_20", "pct_ma60_d20",
           "pct_hi20", "lowvol_streak", "emotion_down_streak"]
C_EXTRA = ["g1_depth", "g1_ddur", "g1_vel20", "g1_breadth", "g2_depth",
           "g2_vel20", "g3_depth", "g1_reacc"]
D_EXTRA = ["x_etf_breadth_bad", "x_etf_price_up", "x_lowvol_breadth",
           "x_etf_trend_dn", "x_reacc_breadth"]


def main():
    emo, br, px = load_all()
    F = features(emo, br, px)
    F.to_parquet(f"{D}/MACRO_RISK_PIT_FEATURES.parquet")
    # labels per index
    lab = {}
    for k in ["sse", "szse", "cyb", "alla"]:
        p = px[k].ffill()
        lab[k] = {"px": p, "fwd": fwd_labels(p),
                  "dd120": p / p.rolling(120, min_periods=30).max() - 1}
    # independent cycles (dd10 enter / dd>-5% exit)
    cyc_rows, events = [], []
    for k, v in lab.items():
        for c in cycles_from_dd(v["dd120"]):
            seg = v["dd120"].iloc[c["start_i"]:c["end_i"] + 1]
            t_i = seg.idxmin()
            cyc_rows.append({"obj": k, "cycle_id": c["cycle_id"],
                "first_dd10": str(c["first_cross"])[:10],
                "trough": str(t_i)[:10],
                "max_dd": round(float(seg.min()), 4),
                "status": c["status"]})
            events.append({"obj": k, "cycle_id": c["cycle_id"],
                           "onset": c["first_cross"], "trough": t_i})
    cycdf = pd.DataFrame(cyc_rows)
    cycdf.to_csv("2026_INDEPENDENT_RISK_CYCLES.csv", index=False)
    print("cycles:", cycdf.groupby("obj").size().to_dict())
    print(cycdf[cycdf.first_dd10 >= "2026"].to_string(index=False))
    # monthly event timeline 2026
    tl = []
    for k, v in lab.items():
        p = v["px"]["2026"]
        for mo, s in p.groupby(p.index.month):
            tl.append({"obj": k, "month": mo,
                       "ret": round(float(s.iloc[-1] / s.iloc[0] - 1), 4),
                       "min_dd": round(float(s.min() /
                        s.iloc[0] - 1), 4),
                       "dd120_end": round(float(v["dd120"].loc[
                        s.index[-1]]), 4)})
    pd.DataFrame(tl).to_csv("2026_MARKET_EVENT_TIMELINE.csv", index=False)
    # ---------- models ----------
    tr_end = "2023-12-31"
    res_rows, replay = [], {}
    for k in ["sse", "szse", "cyb", "alla"]:
        v = lab[k]
        y = pd.Series(np.where(np.isnan(v["fwd"][60][2]), np.nan,
                      (v["fwd"][60][2] <= -0.10).astype(float)),
                      index=F.index)
        # embargo: train features end ~60 trading days before valid start
        emb = F.index < (pd.Timestamp("2024-01-01") - pd.Timedelta(days=90))
        trm = (F.index <= tr_end) & ~y.isna().values & emb
        models = {
            "A": A_COLS(k), "B": A_COLS(k) + B_EXTRA,
            "C": A_COLS(k) + B_EXTRA + C_EXTRA,
            "D": A_COLS(k) + B_EXTRA + C_EXTRA + D_EXTRA}
        for mn, cols in models.items():
            X = F[cols].replace([np.inf, -np.inf], np.nan).fillna(0).values
            w, mu, sd = logit_fit(X[trm], y[trm].values)
            pr = logit_pred(X, w, mu, sd)
            replay[(k, mn)] = pd.Series(pr, index=F.index)
            for seg, msk in [("valid_2425",
                              (F.index >= "2024-01-01") &
                              (F.index < "2026-01-01") & ~y.isna()),
                             ("replay_26",
                              (F.index >= "2026-01-01") & ~y.isna())]:
                if msk.sum() < 30:
                    continue
                res_rows.append({"obj": k, "model": mn, "seg": seg,
                    "n": int(msk.sum()),
                    "ap": round(ap(y[msk], pr[msk]), 3),
                    "brier": round(float(np.mean((pr[msk] -
                        y[msk].values) ** 2)), 4)})
        # Model 0: emotion_score percentile (inverted) — not calibrated
        e = F.emotion
        p0 = 1 - e.expanding(min_periods=250).apply(
            lambda s: pd.Series(s).rank(pct=True).iloc[-1]).reindex(F.index)
        replay[(k, "0")] = p0
        msk = (F.index >= "2024-01-01") & (F.index < "2026-01-01") & ~y.isna()
        if msk.sum() > 30:
            res_rows.append({"obj": k, "model": "0_emotion",
                "seg": "valid_2425", "n": int(msk.sum()),
                "ap": round(ap(y[msk], p0[msk]), 3),
                "brier": None})
    res = pd.DataFrame(res_rows)
    res.to_csv("MODEL_RESULTS.csv", index=False)
    print(res.to_string(index=False))
    # replay snapshots: percentile-normalized risk score per model
    snaps = []
    for (k, mn), pr in replay.items():
        hist = pr[F.index <= "2026-06-30"]
        for t, s in pr[F.index >= "2026-07-01"].items():
            pct = (hist <= s).mean()
            st = ("NORMAL" if pct < 0.6 else "WATCH" if pct < 0.8 else
                  "ELEVATED" if pct < 0.9 else "HIGH")
            snaps.append({"date": str(t)[:10], "obj": k, "model": mn,
                          "score_pct": round(pct, 3), "state": st})
    pd.DataFrame(snaps).to_csv("REPLAY_DAILY_SNAPSHOTS.csv", index=False)
    print("snapshots:", len(snaps))


if __name__ == "__main__":
    main()
