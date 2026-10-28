"""ETF-FLOW-POC-01 step 3 — compute cumulative net creations.

Method (documented assumptions in POC_CONCLUSION.md):
  daily_net_creation_yi = delta_shares * valuation / 1e8
  valuation            = daily close (sina) — primary bulk basis
  cumulative           = running sum per holder group

Scope: A-share equity ETFs. SSE etf_type in {跨市, 单市}; SZSE funds
kept unless the name matches money/bond/commodity/QDII patterns.
Unknown-classification funds are kept in a separate bucket, never
forced into personal/institution.

Quality gates: share jumps flagged; drop >40% in one day treated as
suspected corporate action (折算/合并) — excluded from the flow
estimate and counted in the audit.
"""
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
DATA = HERE / "data"

NON_EQUITY_NAME = re.compile(
    r"货币|债|保证金|快线|快钱|黄金|白银|原油|豆粕|"
    r"纳指|纳斯达克|标普|日经|德国|法国|东南亚|沙特|"
    r"恒生|港股|中概|海外|QDII|H股|香港|亚太|全球", re.I)


def load_shares() -> pd.DataFrame:
    frames = []
    for f in ("sse_etf_shares.csv", "szse_etf_shares.csv"):
        p = DATA / f
        if p.exists():
            frames.append(pd.read_csv(p, dtype={"fund_code": str}))
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["fund_code"] = df["fund_code"].str.zfill(6)
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    return df.dropna(subset=["shares"])


def equity_universe(shares: pd.DataFrame) -> set[str]:
    """A-share equity ETF universe: SSE 跨市/单市 + SZSE funds whose
    name does not match non-equity patterns."""
    last = (shares.sort_values("date")
            .groupby("fund_code").tail(1)
            .set_index("fund_code"))
    keep = set()
    for code, row in last.iterrows():
        et = str(row.get("etf_type") or "")
        name = str(row.get("name") or "")
        if NON_EQUITY_NAME.search(name):
            continue
        if et in {"跨市", "单市", "szse"}:
            keep.add(code)
    return keep


def load_prices(codes: set[str]) -> pd.DataFrame:
    """Valuation basis: unit NAV (天天基金 pingzhongdata) primary;
    sina/tencent close price fallback for funds without NAV."""
    frames = []
    for code in codes:
        np_ = DATA / "naval" / f"{code}.csv"
        pp = DATA / "prices" / f"{code}.csv"
        if np_.exists():
            d = pd.read_csv(np_, dtype={"date": str})
            d["fund_code"] = code
            frames.append(d.rename(columns={"nav": "close"})
                          [["fund_code", "date", "close"]])
        elif pp.exists():
            d = pd.read_csv(pp, dtype={"date": str})
            d["fund_code"] = code
            frames.append(d[["fund_code", "date", "close"]])
    if not frames:
        return pd.DataFrame(columns=["fund_code", "date", "close"])
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"])


def classify_holders(codes: set[str]) -> pd.DataFrame:
    """Latest semi-annual disclosure <= today: inst_pct > 50 ->
    institution-led; indiv_pct > 50 -> personal-led; else mixed;
    no disclosure -> unknown."""
    rows = []
    for code in sorted(codes):
        p = DATA / "holder_structure" / f"{code}.csv"
        if not p.exists():
            rows.append({"fund_code": code, "holder_class": "unknown",
                         "inst_pct": np.nan, "indiv_pct": np.nan,
                         "disclosure_date": None})
            continue
        d = pd.read_csv(p, dtype={"disclosure_date": str})
        if d.empty:
            rows.append({"fund_code": code, "holder_class": "unknown",
                         "inst_pct": np.nan, "indiv_pct": np.nan,
                         "disclosure_date": None})
            continue
        last = d.iloc[-1]
        inst = float(str(last["inst_pct"]).rstrip("%") or "nan")
        indiv = float(str(last["indiv_pct"]).rstrip("%") or "nan")
        cls = ("institution" if inst > 50 else
               "personal" if indiv > 50 else "mixed")
        rows.append({"fund_code": code, "holder_class": cls,
                     "inst_pct": inst, "indiv_pct": indiv,
                     "disclosure_date": last["disclosure_date"]})
    return pd.DataFrame(rows)


def compute_flows(shares: pd.DataFrame, prices: pd.DataFrame,
                  codes: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = shares[shares["fund_code"].isin(codes)].copy()
    s = s.sort_values(["fund_code", "date"])
    s["prev_shares"] = s.groupby("fund_code")["shares"].shift(1)
    s["prev_date"] = s.groupby("fund_code")["date"].shift(1)
    s["d_shares"] = s["shares"] - s["prev_shares"]
    # first observation inside the window (fund appeared after the
    # window's first trading day) = listing creation (IPO 份额);
    # funds already present at window start contribute a 0 baseline.
    s["is_first"] = s["prev_shares"].isna()
    w0 = s["date"].min()
    s.loc[s["is_first"] & (s["date"] > w0), "d_shares"] = s["shares"]
    s["is_ipo_creation"] = s["is_first"] & (s["date"] > w0)
    s["pct_chg"] = np.where(s["prev_shares"] > 0,
                            s["d_shares"] / s["prev_shares"], np.nan)
    # suspected corporate action: >40% single-day drop (折算/合并 or
    # delisting tail); large creations are normal for hot ETFs.
    s["corp_action_suspect"] = s["pct_chg"] < -0.40

    px = prices.rename(columns={"close": "valuation"})
    s = s.merge(px, on=["fund_code", "date"], how="left")
    # fallback valuation: previous known close (fund suspended that day)
    s = s.sort_values(["fund_code", "date"])
    s["valuation"] = s.groupby("fund_code")["valuation"].ffill()
    s["flow_yi"] = s["d_shares"] * s["valuation"] / 1e8
    s.loc[s["corp_action_suspect"], "flow_yi"] = np.nan
    return s, s[s["corp_action_suspect"]]


def main() -> None:
    shares = load_shares()
    codes = equity_universe(shares)
    prices = load_prices(codes)
    holders = classify_holders(codes)
    holders.to_csv(HERE / "ETF_HOLDER_CLASSIFICATION.csv", index=False)

    flows, corp = compute_flows(shares, prices, codes)
    flows.to_csv(DATA / "etf_daily_flows.csv", index=False)
    corp.to_csv(DATA / "corp_action_suspects.csv", index=False)

    cls_map = holders.set_index("fund_code")["holder_class"]
    flows["holder_class"] = flows["fund_code"].map(cls_map)
    daily = (flows.groupby(["date", "holder_class"])["flow_yi"]
             .sum().unstack(fill_value=0.0).sort_index())
    cum = daily.cumsum()
    daily.to_csv(DATA / "daily_flow_by_class.csv")
    cum.to_csv(DATA / "cum_flow_by_class.csv")
    print("funds:", len(codes),
          "| priced:", prices["fund_code"].nunique(),
          "| holder:", holders["holder_class"].value_counts().to_dict(),
          "| dates:", shares["date"].min().date(), "->",
          shares["date"].max().date())
    print("corp-action suspects:", len(corp))
    print(cum.tail(3).round(1).to_string())


if __name__ == "__main__":
    sys.exit(main())
