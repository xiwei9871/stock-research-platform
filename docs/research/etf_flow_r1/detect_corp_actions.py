"""R1.1 reproducible corporate-action detector.

Regenerates data/corp_action_audit.csv from etf_daily_flows_v2.csv.

Detection rule (reconstructed from R1 audit semantics, verified on 510310):
  r_sh    = shares / prev_shares          (share-jump ratio, event day)
  r_nav   = valuation / nav_before        (NAV ratio, event day)
  r_nav_prev / r_nav_next = r_nav shifted -1 / +1 within fund
  share_jump   : r_sh < 0.67 or > 1.5
  nav_extreme(x): x < 0.88 or x > 1.14
  same_day  : share_jump AND nav_extreme(r_nav)
  cross_prev: share_jump AND ~nav_extreme(r_nav) AND nav_extreme(r_nav_prev)

Layering `status`:
  official_confirmed : rows with a cited official announcement (510310).
  algorithm_split    : net-asset continuity closes (ratio within [0.9, 1.1])
  unverified         : does not close -> still masked, but NOT called a
                       confirmed corporate action; covered by sensitivity.
"""
import numpy as np
import pandas as pd

SRC = "../etf_flow_poc02/data/etf_daily_flows_v2.csv"
OUT = "data/corp_action_audit.csv"

SH_LO, SH_HI = 0.67, 1.5
NAV_LO, NAV_HI = 0.88, 1.14
CONT_LO, CONT_HI = 0.90, 1.10

OFFICIAL = {
    ("510310", "2024-09-20"):
        "份额合并(1:2.0005), 易方达公告2024-09-18; 上交所结果公告 "
        "510310_20240923_G18B: 合并比例0.49977589, 场内62347244017份, 净值3.2021",
}


def main():
    d = pd.read_csv(SRC, low_memory=False)
    d["fund_code"] = d.fund_code.astype(str).str.zfill(6)
    d = d.sort_values(["fund_code", "date"]).reset_index(drop=True)

    g = d.groupby("fund_code")
    d["r_sh"] = d.shares / d.prev_shares
    d["r_nav"] = d.valuation / d.nav_before
    d["r_nav_prev"] = g.r_nav.shift(1)
    d["r_nav_next"] = g.r_nav.shift(-1)
    # valuation two days back, for cross_prev continuity check
    d["val_m2"] = g.valuation.shift(2)
    d["sh_m1"] = g.shares.shift(1)

    nav_ex = lambda s: (s < NAV_LO) | (s > NAV_HI)
    sh_ex = (d.r_sh < SH_LO) | (d.r_sh > SH_HI)
    kind = np.where(nav_ex(d.r_nav), "same_day",
                    np.where(nav_ex(d.r_nav_prev), "cross_prev", ""))
    cand = d[sh_ex & (kind != "")].copy()
    cand["kind"] = kind[sh_ex & (kind != "")]

    # net-asset continuity: does post-event mv match pre-event mv?
    pre_mv = np.where(cand.kind == "cross_prev",
                      cand.sh_m1 * cand.val_m2,          # shares(t-1)*nav(t-2)
                      cand.prev_shares * cand.nav_before)  # shares(t-1)*nav(t-1)
    post_mv = cand.shares * cand.valuation
    cand["cont_ratio"] = post_mv / pre_mv
    closes = cand.cont_ratio.between(CONT_LO, CONT_HI)

    cand["status"] = np.where(
        closes, "algorithm_split", "unverified")
    key = list(zip(cand.fund_code, cand.date))
    cand.loc[[k in OFFICIAL for k in key], "status"] = "official_confirmed"
    cand["official_note"] = [OFFICIAL.get(k, "") for k in key]

    cols = ["date", "fund_code", "name", "etf_type", "shares", "prev_shares",
            "prev_date", "d_shares", "is_first", "nav_start",
            "is_ipo_creation", "is_missing_first", "pct_chg", "valuation",
            "nav_before", "next_shares", "corp_suspect", "flow_yi",
            "excluded_reason", "is_corp_action", "ipo_creation_yi",
            "excluded_flow_yi", "class_fixed", "class_pit",
            "r_nav", "r_sh", "r_nav_prev", "r_nav_next", "kind",
            "cont_ratio", "status", "official_note"]
    cand["year"] = cand.date.str[:4]
    cand[cols + ["year"]].to_csv(OUT, index=False)
    print(cand.status.value_counts())
    print(cand.kind.value_counts())
    print("total:", len(cand))


if __name__ == "__main__":
    main()
