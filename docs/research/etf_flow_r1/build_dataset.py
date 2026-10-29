"""R1 dataset builder: universe/groups + corrected flows + group AUM + proxy indices.

Reads POC-02.1 etf_daily_flows_v2.csv (gitignored input, hash recorded in
DATA_QUALITY_GATE.md). Applies the 148 cross-day/same-day corporate-action
hits (data_crossday_corp_actions.csv): masks the fund on BOTH the NAV-jump
day and the share-jump day from flow AND AUM aggregation (stale share count
makes both sides wrong), zeroes its flow on the share-jump day.

Outputs (gitignored intermediates in data/):
  fund_day.csv      per fund-date: flow_use, mv, nav_ret (corp-masked)
  group_daily.csv   per group-date: flow_yi, aum_yi, idx_ret, n_funds
  universe csv      committed: ETF_UNIVERSE_AND_GROUPS.csv
"""
import re
import numpy as np
import pandas as pd

DATA = "../etf_flow_poc02/data"
OUT = "data"

NON_EQUITY = ("债", "国开", "短融", "城投", "利率", "货币", "添益", "日利",
              "黄金", "白银", "豆粕", "原油", "饲料", "能化", "REIT",
              "纳指", "标普", "恒生", "中概", "港股", "日经", "德国",
              "法国", "沙特", "东南亚", "纳斯达克", "道琼斯", "QDII",
              "美元", "亚太", "全球", "美国", "海外", "中韩", "日本",
              "期货", "国货", "湾区")
G2_CODES = {"510300", "510310", "510330", "159919"}
SSE50_CODES = {"510050"}
KW = {
    "G5_semiconductor": "半导体|芯片|集成电路|晶圆|封测",
    "G6_ai_compute": "人工智能|AI|算力|云计算|大数据|通信|5G|信创|数字|云50|软件服务",
    "G7_robot": "机器人|智能制造|工业母机|数控",
    "G8_softinfo": "软件|信息技术|计算机|互联网|游戏|传媒|在线|VR|金融科技|电子|消费电子|数据",
    "G4k_star": "科创",
}
BROAD = ("300", "500", "1000", "50", "2000", "A500", "A50", "A100",
         "创业板", "综指", "深100", "上证", "中证", "MSCI", "央企",
         "国企", "红利", "自由现金", "价值", "成长", "等权", "基本面",
         "增强", "指增")


def classify(code, name):
    n = str(name)
    if any(k in n for k in NON_EQUITY):
        return "non_equity"
    if code in G2_CODES:
        return "G2_hs300_head"
    if code in SSE50_CODES:
        return "G9_sse50_head"
    for g, kw in KW.items():
        if re.search(kw, n, re.I):
            return g
    if any(k.lower() in n.lower() for k in BROAD):
        return "G3_other_broad"
    return "G1_sector_other"


def main():
    hits = pd.read_csv("data/corp_action_audit.csv",
                       dtype={"fund_code": str})
    hits["fund_code"] = hits["fund_code"].str.zfill(6)
    # only confirmed + algorithm-split events are masked from flow_use;
    # unverified stays in series but is removed in flow_use_strict
    conf = hits[hits.status.isin(["official_confirmed", "algorithm_split"])]
    unv = hits[hits.status == "unverified"]
    hit_days = set(zip(conf.fund_code, conf.date))
    unv_days = set(zip(unv.fund_code, unv.date))
    # NAV-jump day = share-jump day - 1 trading day (per fund calendar)
    nav_jump = conf[conf.kind == "cross_prev"].copy()

    d = pd.read_csv(f"{DATA}/etf_daily_flows_v2.csv", low_memory=False)
    d["fund_code"] = d["fund_code"].astype(str).str.zfill(6)
    d = d.sort_values(["fund_code", "date"]).reset_index(drop=True)

    uni = (d.drop_duplicates("fund_code")[["fund_code", "name", "etf_type",
                                          "is_first", "nav_start"]]
             .rename(columns={"nav_start": "first_seen"}))
    uni["group"] = [classify(c, n) for c, n in
                    zip(uni.fund_code, uni.name)]
    uni.to_csv("ETF_UNIVERSE_AND_GROUPS.csv", index=False)
    # tech-group audit sample: 25 per group with name-based flag heuristic
    aud = []
    for g in ("G4k_star", "G5_semiconductor", "G6_ai_compute",
              "G7_robot", "G8_softinfo"):
        sub = uni[uni.group == g]
        for _, r in sub.iterrows():
            n = str(r["name"])
            flag = ("ok" if re.search(KW[g], n, re.I) else "name_miss")
            aud.append({"group": g, "fund_code": r.fund_code,
                        "name": n, "audit_flag": flag})
    pd.DataFrame(aud).to_csv("TECH_GROUP_AUDIT.csv", index=False)
    print(uni.group.value_counts())
    uni.loc[uni.group != "non_equity", "group"].to_frame()  # noop

    # map NAV-jump day per fund (prev row before share-jump day)
    d["hit_share"] = list(zip(d.fund_code, d.date))
    d["hit_share"] = d["hit_share"].isin(hit_days)
    # prev NAV-jump row: for each cross_prev hit, the row index -1 within fund
    hit_idx = d.index[d.hit_share & d.date.isin(
        set(nav_jump.date))]
    nav_jump_idx = set()
    for i in hit_idx:
        if i > 0 and d.fund_code.iloc[i - 1] == d.fund_code.iloc[i]:
            nav_jump_idx.add(i - 1)
    d["mask_day"] = d.hit_share | d.index.isin(nav_jump_idx)

    inc = d.excluded_reason.isna() | (d.excluded_reason == "")
    # flow_use: real flow, zero on confirmed/algo-split share-jump day
    d["flow_use"] = np.where(d.hit_share | ~inc, 0.0, d.flow_yi.fillna(0.0))
    # strict variant: also zero unverified candidates (sensitivity)
    d["unv_day"] = list(zip(d.fund_code, d.date))
    d["unv_day"] = d["unv_day"].isin(unv_days)
    d["flow_use_strict"] = np.where(d.unv_day, 0.0, d.flow_use)
    d["mv"] = d.shares * d.valuation.ffill() / 1e8
    # nav return; masked on both corp days
    g = d.groupby("fund_code")
    d["nav_ret"] = g.valuation.pct_change()
    d.loc[d.mask_day, ["nav_ret", "mv", "flow_use"]] = np.nan

    d.to_parquet(f"{OUT}/fund_day.parquet")
    print("fund_day rows:", len(d), "masked:", int(d.mask_day.sum()))

    eq = d[d.fund_code.isin(uni.loc[uni.group != "non_equity",
                                   "fund_code"])]
    gmap = uni.set_index("fund_code").group
    eq = eq.assign(grp=eq.fund_code.map(gmap))
    daily = (eq.groupby(["grp", "date"])
               .agg(flow_yi=("flow_use", "sum"),
                    aum_yi=("mv", "sum"),
                    n_funds=("fund_code", "nunique")))
    daily["flow_yi"] = daily.flow_yi.fillna(0)
    daily.to_parquet(f"{OUT}/group_daily_raw.parquet")

    # group index proxy: prev-day AUM-weighted mean nav_ret
    eq["mv_prev"] = eq.groupby("fund_code").mv.shift(1)
    eq["w"] = eq.mv_prev * eq.nav_ret
    idx = (eq.groupby(["grp", "date"])
             .agg(wsum=("w", "sum"), wden=("mv_prev", "sum")))
    idx["idx_ret"] = idx.wsum / idx.wden
    idx.to_parquet(f"{OUT}/group_idx_ret.parquet")
    print("groups built:", sorted(set(eq.grp)))


if __name__ == "__main__":
    main()
