"""Build the read-only Market Monitor V2 snapshot from frozen research outputs.

Inputs (all PIT-verified research artifacts, no production DB access):
  docs/research/market_risk_m1/data/MACRO_RISK_PIT_FEATURES.parquet
  docs/research/market_risk_m1/data/emotion_daily.parquet
  docs/research/market_risk_m2/M2_TEMPORAL_FEATURES.parquet  (mcc_osc/mcc_sum)
  docs/research/etf_flow_r31/PIT_CYCLE_DAILY.csv             (per-group daily flow)
  docs/research/etf_flow_r31/PIT_CYCLE_EVENTS.csv            (cycle table)

Outputs (served read-only by market_regime_service):
  docs/market_monitor_v2/data/market_regime_snapshot.parquet
  docs/market_monitor_v2/data/etf_flow_history.parquet
  docs/market_monitor_v2/data/etf_cycles.json
  docs/market_monitor_v2/data/manifest.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
M1 = ROOT / "docs/research/market_risk_m1/data"
M2 = ROOT / "docs/research/market_risk_m2"
R31 = ROOT / "docs/research/etf_flow_r31"
OUT = Path(__file__).parent / "data"

OBJECTS = ["alla", "sse", "szse", "cyb"]

CONT_COLS = [
    "up_share", "up_share20", "dn_share20", "limit_up20", "limit_dn20",
    "amt", "amt_ratio_5_20", "amt_ratio_20_60", "amt_pct20",
    "lowvol20", "lowvol_streak", "pct_ma60", "pct_ma60_20", "pct_ma60_d20",
    "pct_hi20", "breadth_bad_streak",
]
ETF_COLS = [
    "g1_depth", "g1_ddur", "g1_vel20", "g1_reacc",
    "g2_depth", "g2_ddur", "g2_vel20", "g2_reacc",
    "g3_depth", "g3_ddur", "g3_vel20", "g3_reacc",
]
IDX_COLS = [f"{o}_{s}" for o in OBJECTS for s in
            ("ret20", "ret60", "dd120", "vol60", "trend")]
EMO_COLS = ["emotion", "emotion20", "emotion_d5", "emotion_down_streak"]

GROUPS = {
    "G1_all_equity": "g1",
    "G2_hs300_head": "g2",
    "G3_other_broad": "g3",
}


def regime_label(dd: float) -> str:
    if pd.isna(dd):
        return "DATA_MISSING"
    if dd <= -0.20:
        return "DEEP_DECLINE"
    if dd <= -0.10:
        return "DECLINE"
    if dd <= -0.05:
        return "MILD_DRAWDOWN"
    return "NORMAL_RANGE"


def build_market_snapshot() -> pd.DataFrame:
    f = pd.read_parquet(M1 / "MACRO_RISK_PIT_FEATURES.parquet")
    m2 = pd.read_parquet(M2 / "M2_TEMPORAL_FEATURES.parquet")
    f = f.join(m2[["mcc_osc", "mcc_sum"]], how="left")
    cols = [c for c in IDX_COLS + CONT_COLS + EMO_COLS + ETF_COLS
            if c in f.columns] + ["mcc_osc", "mcc_sum"]
    snap = f[cols].copy()
    snap.index = pd.to_datetime(snap.index)
    snap.index.name = "trade_date"
    for o in OBJECTS:
        snap[f"{o}_regime"] = snap[f"{o}_dd120"].map(regime_label)
    # duration in current regime (consecutive trading days)
    for o in OBJECTS:
        lab = snap[f"{o}_regime"]
        grp = (lab != lab.shift()).cumsum()
        snap[f"{o}_regime_days"] = grp.groupby(grp).cumcount() + 1
    return snap


def build_etf_history() -> tuple[pd.DataFrame, dict]:
    daily = pd.read_csv(R31 / "PIT_CYCLE_DAILY.csv", parse_dates=["date"])
    daily = daily[daily.group.isin(GROUPS)].copy()
    daily["gkey"] = daily.group.map(GROUPS)
    daily = daily.sort_values(["gkey", "date"])
    daily["cum_flow"] = daily.groupby(["gkey", "pcyc"]).flow.cumsum()
    daily["cum_depth_pct"] = daily["pdepth"] * 100.0
    daily["cycle_start_aum"] = daily.groupby(
        ["gkey", "pcyc"]).aum.transform("first")
    daily["cum_withdrawal_pct_aum0"] = (
        -daily["cum_flow"] / daily["cycle_start_aum"] * 100.0)
    daily["current_aum"] = daily["aum"]
    keep = ["date", "gkey", "group", "pcyc", "pstate", "flow", "cum_flow",
            "aum", "pdepth", "cum_depth_pct", "ddur", "eelap", "vel5",
            "vel20", "outshare20", "breadth_out", "idx_level",
            "cum_withdrawal_pct_aum0", "cycle_start_aum", "current_aum"]
    hist = daily[keep].rename(columns={"date": "trade_date"})

    cycles = {}
    ev = pd.read_csv(R31 / "PIT_CYCLE_EVENTS.csv") if (
        R31 / "PIT_CYCLE_EVENTS.csv").exists() else pd.DataFrame()
    for g, gkey in GROUPS.items():
        d = hist[hist.gkey == gkey]
        last = d.iloc[-1] if len(d) else None
        entry = {
            "group": g,
            "latest_date": str(last.trade_date)[:10] if last is not None else None,
            "current_cycle": last.pcyc if last is not None else None,
            "current_state": last.pstate if last is not None else None,
            "current_depth_pct": round(float(last.cum_depth_pct), 2)
            if last is not None and not pd.isna(last.cum_depth_pct) else None,
            "cum_flow_latest": round(float(last.cum_flow), 1)
            if last is not None and not pd.isna(last.cum_flow) else None,
            "cycle_start_aum": round(float(last.cycle_start_aum), 1)
            if last is not None and not pd.isna(last.cycle_start_aum)
            else None,
            "current_aum": round(float(last.current_aum), 1)
            if last is not None and not pd.isna(last.current_aum) else None,
            # NOTE: no global max_depth here — a full-history maximum would
            # leak future cycle information into historical queries.  The
            # service computes running maxima per request date instead.
        }
        cycles[gkey] = entry
    return hist, cycles


def _git_sha() -> str:
    try:
        import subprocess
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            capture_output=True, text=True).stdout.strip()
    except Exception:
        return "nogit"


def main(version: str | None = None) -> None:
    ver = version or f"v{_git_sha()}"
    stage = OUT / f".stage-{ver}"
    if stage.exists():
        import shutil
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    snap = build_market_snapshot()
    snap.to_parquet(stage / "market_regime_snapshot.parquet")
    hist, cycles = build_etf_history()
    hist.to_parquet(stage / "etf_flow_history.parquet")
    (stage / "etf_cycles.json").write_text(
        json.dumps(cycles, ensure_ascii=False, indent=1))
    manifest = {
        "snapshot_version": ver,
        "source_parquets": {
            "m1_features": "docs/research/market_risk_m1/data/MACRO_RISK_PIT_FEATURES.parquet",
            "m2_features": "docs/research/market_risk_m2/M2_TEMPORAL_FEATURES.parquet",
            "r31_cycle_daily": "docs/research/etf_flow_r31/PIT_CYCLE_DAILY.csv",
        },
        "rows": {"market_snapshot": int(len(snap)),
                 "etf_history": int(len(hist))},
        "date_range": {
            "market": [str(snap.index.min())[:10],
                       str(snap.index.max())[:10]],
            "etf": [str(hist.trade_date.min())[:10],
                    str(hist.trade_date.max())[:10]],
        },
        "research_baseline": "2a03051df2cde2f333d797711b76f3544f25752f",
        "note": ("cum_depth_pct = cumulative net redemption / cycle-start AUM; "
                 "values >100% mean net redemptions exceeded the AUM measured "
                 "at the cycle start, not that holdings were sold more than "
                 "once."),
    }
    (stage / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1))
    # atomic publish: rename staged dir to the version dir, then update the
    # `current` pointer last so readers never see a half-written snapshot
    target = OUT / ver
    if target.exists():
        import shutil
        shutil.rmtree(target)
    stage.rename(target)
    tmp_ptr = OUT / ".current.tmp"
    tmp_ptr.write_text(ver)
    tmp_ptr.replace(OUT / "current")
    print("snapshot version:", ver)
    print("snapshot rows:", len(snap), "etf rows:", len(hist))
    print("range:", manifest["date_range"])


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
