"""ETF-FLOW-POC-02 — calibrated net-creation computation.

Reads the POC-01 verified raw panel (../etf_flow_poc01/data) and
recomputes flows under four calibrations:

1. Holder classification: `latest-fixed` (POC-01) AND `pit-rolling`
   (a fund's class at date t uses the latest disclosure effective at
   t; disclosure assumed effective 90 days after 截止日 — funds must
   publish SAR/AR within ~60/90 days).
2. First-appearance funds: IPO creation only when the first observed
   share date is within 45 days of the fund's NAV series start
   (fund establishment). Later first-obs = missing-data gap, not IPO.
3. Corp-action suspects (|d_shares/shares| > 40% either direction):
   discriminate by NAV continuity — a 折算/合并 moves NAV inversely
   with shares; a real redemption keeps NAV continuous.
4. Daily coverage accounting: zero-flow vs missing separated;
   missing-amount range estimated via group-median NAV.

Outputs to ./data (gitignored) + root CSVs.
"""
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
SRC = HERE.parent / "etf_flow_poc01" / "data"
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)

PUB_LAG_DAYS = 90          # assumed disclosure effective lag (assumption)
IPO_WINDOW_DAYS = 45       # share-first-vs-NAV-first tolerance
DROP_FLAG = 0.40           # corp-action suspect threshold (down)
JUMP_FLAG = 1.00           # suspected share split (>100% up)
NAV_RATIO_TOL = 0.25       # |nav_ratio - inverse_share_ratio| tolerance

NON_EQUITY_NAME = re.compile(
    r"货币|债|保证金|快线|快钱|黄金|白银|原油|豆粕|"
    r"纳指|纳斯达克|标普|日经|德国|法国|东南亚|沙特|"
    r"恒生|港股|中概|海外|QDII|H股|香港|亚太|全球", re.I)


def load_shares() -> pd.DataFrame:
    frames = []
    for f in ("sse_etf_shares.csv", "szse_etf_shares.csv"):
        frames.append(pd.read_csv(SRC / f, dtype={"fund_code": str}))
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["fund_code"] = df["fund_code"].str.zfill(6)
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    return df.dropna(subset=["shares"])


def equity_universe(shares: pd.DataFrame) -> set[str]:
    last = (shares.sort_values("date")
            .groupby("fund_code").tail(1).set_index("fund_code"))
    keep = set()
    for code, row in last.iterrows():
        et = str(row.get("etf_type") or "")
        name = str(row.get("name") or "")
        if NON_EQUITY_NAME.search(name):
            continue
        if et in {"跨市", "单市", "szse"}:
            keep.add(code)
    return keep


def load_nav(codes: set[str]) -> pd.DataFrame:
    frames = []
    for code in codes:
        np_ = SRC / "naval" / f"{code}.csv"
        pp = SRC / "prices" / f"{code}.csv"
        if np_.exists():
            d = pd.read_csv(np_, dtype={"date": str})
            d["fund_code"] = code
            frames.append(d.rename(columns={"nav": "valuation"})
                          [["fund_code", "date", "valuation"]])
        elif pp.exists():
            d = pd.read_csv(pp, dtype={"date": str})
            d["fund_code"] = code
            frames.append(d.rename(columns={"close": "valuation"})
                          [["fund_code", "date", "valuation"]])
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["valuation"] = pd.to_numeric(df["valuation"], errors="coerce")
    return df.dropna(subset=["valuation"])


def holder_history(code: str) -> pd.DataFrame:
    p = SRC / "holder_structure" / f"{code}.csv"
    if not p.exists():
        return pd.DataFrame(
            columns=["effective_from", "holder_class", "inst_pct",
                     "indiv_pct", "disclosure_date"])
    d = pd.read_csv(p, dtype={"disclosure_date": str})
    if d.empty:
        return pd.DataFrame(
            columns=["effective_from", "holder_class", "inst_pct",
                     "indiv_pct", "disclosure_date"])
    d = d.copy()
    d["inst_pct"] = pd.to_numeric(
        d["inst_pct"].astype(str).str.rstrip("%"), errors="coerce")
    d["indiv_pct"] = pd.to_numeric(
        d["indiv_pct"].astype(str).str.rstrip("%"), errors="coerce")
    d["disclosure_date"] = pd.to_datetime(d["disclosure_date"])
    d = d.sort_values("disclosure_date")
    d["holder_class"] = np.where(
        d["inst_pct"] > 50, "institution",
        np.where(d["indiv_pct"] > 50, "personal", "mixed"))
    # 截止日 + assumed publication lag = earliest legal-use date
    d["effective_from"] = d["disclosure_date"] + pd.Timedelta(
        days=PUB_LAG_DAYS)
    return d[["effective_from", "holder_class", "inst_pct",
              "indiv_pct", "disclosure_date"]]


def build_classifications(codes: set[str]):
    """Return (fixed_map, pit_table) for the universe."""
    fixed, pit_rows = {}, []
    for code in sorted(codes):
        h = holder_history(code)
        if h.empty:
            fixed[code] = "unknown"
            continue
        fixed[code] = h.iloc[-1]["holder_class"]
        tmp = h.assign(fund_code=code)
        pit_rows.append(tmp)
    pit = (pd.concat(pit_rows, ignore_index=True) if pit_rows
           else pd.DataFrame(columns=["effective_from", "holder_class",
                                      "inst_pct", "indiv_pct",
                                      "disclosure_date", "fund_code"]))
    return fixed, pit


def pit_class_series(flows: pd.DataFrame, pit: pd.DataFrame) -> pd.Series:
    """PIT-rolling class per (fund_code,date) via asof merge; funds
    whose first effective disclosure is after the flow date are
    'pre_disclosure', funds with no disclosure at all are 'unknown'."""
    f = flows[["fund_code", "date"]].copy()
    f["_orig"] = f.index
    f = f.sort_values("date")
    p = pit.sort_values("effective_from")
    m = pd.merge_asof(
        f, p[["fund_code", "effective_from", "holder_class"]],
        left_on="date", right_on="effective_from", by="fund_code",
        direction="backward")
    cls = m["holder_class"].fillna("pre_disclosure")
    has_hist = set(pit["fund_code"].unique())
    cls[~m["fund_code"].isin(has_hist)] = "unknown"
    cls.index = m["_orig"]
    return cls.sort_index()


def review_corp_actions(flows: pd.DataFrame) -> pd.DataFrame:
    """Verdicts per flagged row:
    - corporate_action: NAV jumps inversely with shares (拆分/合并/折算)
    - data_anomaly: share move reverts next day (exchange data glitch)
    - redemption_verified: NAV continuous AND new share level persists
    - redemption_probable: NAV continuous, no next-day evidence
    - pending_review: insufficient NAV/share evidence either way
    """
    sus = flows[flows["corp_suspect"]].copy()
    verdicts = []
    for _, r in sus.iterrows():
        nb, na = r.get("nav_before"), r.get("valuation")
        prev, cur, nxt = r["prev_shares"], r["shares"], r["next_shares"]
        if pd.isna(nb) or pd.isna(na) or nb <= 0 or cur <= 0 or prev <= 0:
            verdicts.append("pending_review")
            continue
        nav_ratio = na / nb
        inv_share = prev / cur
        if abs(nav_ratio - inv_share) / inv_share <= NAV_RATIO_TOL:
            verdicts.append("corporate_action")
            continue
        reverted = (pd.notna(nxt) and nxt > 0
                    and abs(nxt - prev) / prev <= 0.12)
        if reverted:
            verdicts.append("data_anomaly")
            continue
        if abs(nav_ratio - 1.0) <= 0.15:
            persists = pd.isna(nxt) or abs(nxt - cur) / cur <= 0.5
            verdicts.append("redemption_verified" if persists
                            else "redemption_probable")
        else:
            verdicts.append("pending_review")
    sus["verdict"] = verdicts
    sus["nav_ratio"] = sus["valuation"] / sus["nav_before"]
    sus["share_ratio"] = sus["prev_shares"] / sus["shares"]
    return sus


def compute() -> None:
    shares = load_shares()
    codes = equity_universe(shares)
    nav = load_nav(codes)
    fixed, pit = build_classifications(codes)

    s = shares[shares["fund_code"].isin(codes)].copy()
    s = s.sort_values(["fund_code", "date"])
    s["prev_shares"] = s.groupby("fund_code")["shares"].shift(1)
    s["prev_date"] = s.groupby("fund_code")["date"].shift(1)
    s["d_shares"] = s["shares"] - s["prev_shares"]

    # --- IPO vs missing-data first observation ---
    nav_start = (nav.groupby("fund_code")["date"].min())
    s["is_first"] = s["prev_shares"].isna()
    s["nav_start"] = s["fund_code"].map(nav_start)
    gap_days = (s["date"] - s["nav_start"]).dt.days
    s["is_ipo_creation"] = (
        s["is_first"] & (gap_days <= IPO_WINDOW_DAYS))
    s["is_missing_first"] = (
        s["is_first"] & (gap_days > IPO_WINDOW_DAYS))
    s.loc[s["is_ipo_creation"], "d_shares"] = s["shares"]

    # --- valuation + flags ---
    s["pct_chg"] = np.where(s["prev_shares"] > 0,
                            s["d_shares"] / s["prev_shares"], np.nan)
    s = s.merge(nav, on=["fund_code", "date"], how="left")
    s = s.sort_values(["fund_code", "date"])
    s["valuation"] = s.groupby("fund_code")["valuation"].ffill()
    # nav_before = last available valuation BEFORE the event day
    # (ffill first so NAV gaps don't blind the split detector)
    s["nav_before"] = s.groupby("fund_code")["valuation"].shift(1)
    s["next_shares"] = s.groupby("fund_code")["shares"].shift(-1)
    s["corp_suspect"] = (
        (s["pct_chg"] < -DROP_FLAG) | (s["pct_chg"] > JUMP_FLAG)) \
        & ~s["is_ipo_creation"]

    s["flow_yi"] = s["d_shares"] * s["valuation"] / 1e8

    corp = review_corp_actions(s)
    corp.to_csv(DATA / "corp_review_raw.csv", index=False)
    excl = {v: set(corp.loc[corp["verdict"] == v,
                           ["fund_code", "date"]].itertuples(index=False))
            for v in ("corporate_action", "data_anomaly", "pending_review")}
    s["excluded_reason"] = ""
    keys = list(zip(s["fund_code"], s["date"]))
    for reason, ids in excl.items():
        m = [k in ids for k in keys]
        s.loc[m, "excluded_reason"] = reason
    s["is_corp_action"] = s["excluded_reason"] != ""
    s["ipo_creation_yi"] = np.where(
        s["is_ipo_creation"], s["flow_yi"], np.nan)
    s["excluded_flow_yi"] = np.where(s["is_corp_action"], s["flow_yi"],
                                   np.nan)
    s.loc[s["is_corp_action"], "flow_yi"] = np.nan
    s.loc[s["is_missing_first"], "flow_yi"] = np.nan  # not a creation
    s.loc[s["is_ipo_creation"], "flow_yi"] = np.nan  # 募集认购≠申购

    # --- classification lanes ---
    s["class_fixed"] = s["fund_code"].map(fixed)
    s["class_pit"] = pit_class_series(s, pit)
    s.to_csv(DATA / "etf_daily_flows_v2.csv", index=False)

    # --- daily coverage accounting ---
    grp = s.groupby("date")
    cov = pd.DataFrame({
        "funds_reported": grp["fund_code"].nunique(),
        "funds_priced": grp.apply(
            lambda g: g["valuation"].notna().sum()),
        "zero_flow_days": grp.apply(
            lambda g: (g["d_shares"] == 0).sum()),
        "missing_valuation": grp.apply(
            lambda g: (g["d_shares"].notna()
                       & g["valuation"].isna()).sum()),
        "excluded_suspect_rows": grp["is_corp_action"].sum(),
        "excluded_suspect_yi": grp["excluded_flow_yi"].sum(),
        "excluded_missing_first": grp["is_missing_first"].sum(),
        "excluded_ipo_yi": grp["ipo_creation_yi"].sum(),
    })
    med_nav = (nav.groupby("date")["valuation"].median()
               .rename("med_nav"))
    cov = cov.join(med_nav)
    # missing amount bound: missing d_shares x [min nav, max nav] band
    miss = s[(s["d_shares"].notna()) & s["valuation"].isna()] \
        .groupby("date")["d_shares"].sum()
    nav_q = nav.groupby("date")["valuation"].agg(["min", "max"])
    cov["missing_flow_min_yi"] = (miss * nav_q["min"] / 1e8)
    cov["missing_flow_max_yi"] = (miss * nav_q["max"] / 1e8)
    cov.to_csv(DATA / "daily_coverage.csv")

    # --- cumulative per variant ---
    for cname in ("class_fixed", "class_pit"):
        d = s.copy()
        d["cls"] = d[cname]
        daily = (d.groupby(["date", "cls"])["flow_yi"].sum()
                 .unstack(fill_value=0.0).sort_index())
        daily.to_csv(DATA / f"daily_flow_{cname}.csv")
        daily.cumsum().to_csv(DATA / f"cum_flow_{cname}.csv")

    print("funds:", len(codes),
          "| ipo:", int(s["is_ipo_creation"].sum()),
          "| missing_first:", int(s["is_missing_first"].sum()),
          "| corp:", s["is_corp_action"].sum(),
          "| corp verdicts:",
          corp["verdict"].value_counts().to_dict())
    print("class_fixed:", pd.Series(fixed).value_counts().to_dict())
    cumf = pd.read_csv(DATA / "cum_flow_class_fixed.csv",
                       index_col=0).tail(1)
    cump = pd.read_csv(DATA / "cum_flow_class_pit.csv",
                       index_col=0).tail(1)
    print("fixed tail:", cumf.round(1).to_dict("records"))
    print("pit tail:", cump.round(1).to_dict("records"))


if __name__ == "__main__":
    sys.exit(compute())
