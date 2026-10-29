"""R2.1.2 event-level audit. Reads frozen r211 outputs; definitions fixed in
EVENT_DEFINITION.md before computing coverage."""
import numpy as np
import pandas as pd

WARN = {"WATCH", "ELEVATED", "HIGH_PRESSURE"}


def load():
    d = pd.read_csv("../WARNING_STATE_DAILY.csv", index_col=0)
    d.index = pd.to_datetime(d.index)
    return d


def drawdown(px, lookback=120):
    peak = px.rolling(lookback, min_periods=20).max()
    return px / peak - 1, peak


def cycles(dd, px, idx, rec_dd=-0.05, rec_days=10, rec_hi=True):
    """Level-B cycles per EVENT_DEFINITION.md."""
    out = []
    i, n = 0, len(dd)
    while i < n:
        if dd[i] <= -0.10:
            pk_i = max(0, i - 119) + int(np.nanargmax(px[max(0, i - 119):i + 1]))
            j, trough_i, dd15 = i, i, None
            status, rec_i = "ONGOING", None
            while j < n:
                if dd[j] < dd[trough_i]:
                    trough_i = j
                if dd15 is None and dd[j] <= -0.15:
                    dd15 = j
                # end condition
                if rec_hi and px[j] >= px[pk_i] * 1.0 and j > i:
                    status, rec_i = "COMPLETED", j
                    break
                if j - i >= rec_days and all(dd[j - rec_days + 1:j + 1] > rec_dd):
                    status, rec_i = "COMPLETED", j
                    break
                j += 1
            out.append({"cycle_id": f"C{len(out)+1:02d}",
                        "reference_peak_date": str(idx[pk_i])[:10],
                        "reference_peak_price": round(px[pk_i], 2),
                        "first_dd10_date": str(idx[i])[:10],
                        "first_dd15_date": (str(idx[dd15])[:10]
                                            if dd15 is not None else ""),
                        "trough_date": str(idx[trough_i])[:10],
                        "trough_price": round(px[trough_i], 2),
                        "maximum_drawdown": round(dd[trough_i], 4),
                        "i_onset": i, "i_trough": trough_i,
                        "i_end": j, "dd15_i": dd15,
                        "cycle_status": status,
                        "recovery_date": (str(idx[rec_i])[:10]
                                          if rec_i is not None else ""),
                        "right_censored": status == "ONGOING",
                        "merge_reason": "dd recovery" if rec_i else
                        "still in drawdown at data end"})
            i = max(j, i + 1)
        else:
            i += 1
    return out


def episodes(d):
    eps, cur, s0 = [], None, 0
    st = d.state.values
    for i in range(len(d) + 1):
        s = st[i] if i < len(d) else "END"
        if cur is None and s in WARN:
            cur, s0 = s, i
        elif cur is not None and s not in WARN:
            seg = d.iloc[s0:i]
            firsts = {}
            for lv in ["WATCH", "ELEVATED", "HIGH_PRESSURE"]:
                m = np.flatnonzero((seg.state == lv).values)
                firsts[lv] = str(seg.index[m[0]])[:10] if len(m) else ""
            eps.append({"ep_id": f"E{len(eps)+1:02d}",
                        "start": str(seg.index[0])[:10], "i0": s0,
                        "end": str(seg.index[-1])[:10], "i1": i - 1,
                        "release_date": (str(d.index[i])[:10]
                                         if i < len(d) else ""),
                        "dur_days": i - s0,
                        "first_watch": firsts["WATCH"],
                        "first_elevated": firsts["ELEVATED"],
                        "first_high": firsts["HIGH_PRESSURE"],
                        "peak_state": ("HIGH_PRESSURE" if
                                       (seg.state == "HIGH_PRESSURE").any() else
                                       "ELEVATED" if
                                       (seg.state == "ELEVATED").any() else
                                       "WATCH"),
                        "WP_peak": round(seg.WP.max(), 1),
                        "idx_ret": round(seg.hs300.iloc[-1] /
                                         seg.hs300.iloc[0] - 1, 4),
                        "idx_maxdd": round((seg.hs300 /
                                            seg.hs300.cummax() - 1).min(), 4)})
            cur = None
    return eps


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(c - h, 3), round(c + h, 3))


def main():
    d = load()
    d["_px"] = d.hs300
    dd, peak = drawdown(d._px)
    d["_dd"] = dd.values
    idx = d.index
    n = len(d)

    variants = {"S1": dict(rec_dd=-0.05, rec_days=10, rec_hi=True),
                "S2": dict(rec_dd=-0.03, rec_days=20, rec_hi=True),
                "S3": dict(rec_dd=-0.05, rec_days=10**9, rec_hi=True)}
    cycs = {}
    for k, kw in variants.items():
        cycs[k] = cycles(dd.values, d._px.values, idx, **kw)
    base = cycs["S1"]
    df_c = pd.DataFrame(base)
    df_c["n_cycles_S2"] = len(cycs["S2"])
    df_c["n_cycles_S3"] = len(cycs["S3"])
    df_c["source_index"] = "CSI300"
    df_c.drop(columns=["i_onset", "i_trough", "i_end", "dd15_i"]
              ).to_csv("INDEPENDENT_RISK_CYCLES.csv", index=False)
    print("cycles S1/S2/S3:", [len(cycs[k]) for k in variants])

    eps = episodes(d)
    df_e = pd.DataFrame(eps).drop(columns=["i0", "i1"])
    df_e.to_csv("WARNING_EPISODES.csv", index=False)

    # coverage per cycle
    cov_rows = []
    for c in base:
        oi = c["i_onset"]
        active = d.state.iloc[oi] in WARN
        prev = {}
        for w in (5, 20, 60):
            seg = d.state.iloc[max(0, oi - w):oi + 1]
            prev[w] = bool(seg.isin(WARN).any())
        # episode covering or most recent before onset
        ep_act = next((e for e in eps if e["i0"] <= oi <= e["i1"]), None)
        ep_last = next((e for e in reversed(eps) if e["i1"] < oi), None)
        ep = ep_act or ep_last
        row = {"cycle_id": c["cycle_id"], "onset": c["first_dd10_date"],
               "dd15": c["first_dd15_date"], "status": c["cycle_status"],
               "active_at_onset": active,
               "warn_in_5d": prev[5], "warn_in_20d": prev[20],
               "warn_in_60d": prev[60],
               "warn_days_prior60": int(d.state.iloc[max(0, oi - 60):oi]
                                        .isin(WARN).sum()),
               "persisting_ep": ep_act["ep_id"] if ep_act else "",
               "ep_status": ("active_at_onset" if ep_act else
                             "released_before_onset" if ep_last else "none")}
        for lv, k in [("watch", "first_watch"),
                      ("elevated", "first_elevated"),
                      ("high", "first_high")]:
            if ep and ep[k]:
                di = idx.get_loc(pd.Timestamp(ep[k]))
                row[f"lead_{lv}_days"] = oi - di
                row[f"{lv}_date"] = ep[k]
            else:
                row[f"lead_{lv}_days"] = np.nan
                row[f"{lv}_date"] = ""
        # dd15 evaluated at ITS OWN first-cross date
        if c["dd15_i"]:
            j15 = c["dd15_i"]
            ep15 = next((e for e in eps if e["i0"] <= j15 <= e["i1"]), None)
            ep15l = next((e for e in reversed(eps) if e["i1"] < j15), None)
            e15 = ep15 or ep15l
            row["active_at_dd15"] = d.state.iloc[j15] in WARN
            row["dd15_warn_in_20d"] = bool(
                d.state.iloc[max(0, j15 - 20):j15 + 1].isin(WARN).any())
            row["dd15_warn_in_60d"] = bool(
                d.state.iloc[max(0, j15 - 60):j15 + 1].isin(WARN).any())
            row["lead_watch_to_dd15"] = (
                j15 - idx.get_loc(pd.Timestamp(e15["first_watch"]))
                if e15 and e15["first_watch"] else np.nan)
            row["dd15_ep_status"] = ("active_at_onset" if ep15 else
                                     "released_before_onset"
                                     if ep15l else "none")
        else:
            row["active_at_dd15"] = np.nan
            row["dd15_warn_in_20d"] = np.nan
            row["dd15_warn_in_60d"] = np.nan
            row["dd15_ep_status"] = "no_dd15"
        cov_rows.append(row)
    covdf = pd.DataFrame(cov_rows)
    covdf.to_csv("WARNING_COVERAGE_BY_CYCLE.csv", index=False)

    # false alerts per episode
    onset_i = [c["i_onset"] for c in base]
    fa = []
    for e in eps:
        s, en = e["i0"], e["i1"]
        in_dd = dd.iloc[s] <= -0.10
        n60 = [o for o in onset_i if s < o <= s + 60]
        n120 = [o for o in onset_i if s < o <= s + 120]
        after = [o for o in onset_i if en < o <= en + 60]
        cat = ("CENSORED" if s + 60 > n - 1 else
               "in_drawdown" if in_dd else
               "confirmed" if n60 else "false_alert")
        cat120 = ("CENSORED" if s + 120 > n - 1 else
                  "confirmed" if n120 else "false_alert")
        fa.append({"ep_id": e["ep_id"], "start": e["start"],
                   "peak_state": e["peak_state"], "WP_peak": e["WP_peak"],
                   "dur_days": e["dur_days"], "idx_ret": e["idx_ret"],
                   "idx_maxdd": e["idx_maxdd"],
                   "dd_at_start": round(float(dd.iloc[s]), 4),
                   "status_60d": cat, "status_120d": cat120,
                   "days_to_dd10_onset": (n60[0] - s) if n60 else
                   ((n120[0] - s) if n120 else np.nan),
                   "risk_within_60d_after_release": bool(after),
                   "up_move": bool(e["idx_ret"] > 0.10)})
    fadf = pd.DataFrame(fa)
    fadf.to_csv("FALSE_ALERT_AUDIT_R212.csv", index=False)

    # summary table
    unc = [c for c in cov_rows]
    def agg(col):
        v = [r[col] for r in unc]
        return f"{sum(v)}/{len(v)}", wilson(sum(v), len(v))
    summ = []
    for lev, sub, ak, wk, w20 in [
            ("DD10", unc, "active_at_onset", "warn_in_60d", "warn_in_20d"),
            ("DD15", [r for r in unc if r["dd15"]],
             "active_at_dd15", "dd15_warn_in_60d", "dd15_warn_in_20d")]:
        ncy = len(sub)
        row = {"level": lev, "cycles": ncy,
               "active_at_onset": f"{sum(bool(r[ak]) for r in sub)}/{ncy}",
               "warn_20d": f"{sum(bool(r[w20]) for r in sub)}/{ncy}",
               "warn_60d": f"{sum(bool(r[wk]) for r in sub)}/{ncy}",
               "lead_watch_med": np.nanmedian([r["lead_watch_days"]
                                              for r in sub if r["persisting_ep"] or r["ep_status"] != "none"]),
               "lead_elevated_med": np.nanmedian([r["lead_elevated_days"] for r in sub]),
               "lead_high_med": np.nanmedian([r["lead_high_days"] for r in sub]),
               "uncovered": ";".join(r["cycle_id"] for r in sub
                                     if not r[wk])}
        summ.append(row)
    nc = [f for f in fa if f["status_60d"] not in ("CENSORED", "in_drawdown")]
    nc120 = [f for f in fa if f["status_120d"] not in ("CENSORED", "in_drawdown")]
    summ.append({"level": "episodes", "cycles": len(eps),
                 "strict_fa": f"{sum(f['status_60d']=='false_alert' for f in nc)}/{len(nc)}",
                 "loose_fa": f"{sum(f['status_120d']=='false_alert' for f in nc120)}/{len(nc120)}",
                 "fa_dur_med": np.median([f["dur_days"] for f in nc
                                          if f["status_60d"] == "false_alert"])
                 if any(f["status_60d"] == "false_alert" for f in nc) else np.nan,
                 "censored_eps": sum(f["status_60d"] == "CENSORED" for f in fa)})
    sdf = pd.DataFrame(summ)
    sdf.to_csv("RISK_CYCLE_SUMMARY.csv", index=False)
    print(sdf.to_string(index=False))
    print(covdf[["cycle_id", "onset", "active_at_onset", "warn_in_60d",
                 "lead_watch_days", "ep_status"]].to_string(index=False))


if __name__ == "__main__":
    main()
