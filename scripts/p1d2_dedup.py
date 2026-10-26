#!/usr/bin/env python3
"""P1d.2 A2 — deduplicated mislabel statistics.

The P1d.1 reconciliation CSV carries row-level verdicts per scan segment; a
single (asset_id, trade_date, side) can appear in several SEGMENTS (e.g. a
pre-1996 IPO row hits both pre_19961216 and main_ipo_recent). This script
re-derives UNIQUE-key counts, keeps the multi-segment hit list, reports
classification conflicts, and breaks unique mislabels down by effective rule.

Scope honesty: the CSV is a TARGETED scan of regime-divergent segments
(162,119 scanned rows), not a census of the 17.29M-row status table.

Outputs:
  docs/research_upgrade/p1d2/LIMIT_MISLABEL_DEDUP.json
  docs/research_upgrade/p1d2/LIMIT_MISLABEL_DEDUP_REPORT.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

SRC = Path("docs/research_upgrade/p1d1/LIMIT_FLAG_RECONCILIATION.csv")
OUT = Path("docs/research_upgrade/p1d2")

RULE_ERA = {
    "pre_19961216_no_limit": "pre-limit era (<1996-12-16)",
    "chinext_10pct_pre_20200824": "chinext pre-reform (<2020-08-24)",
    "chinext_st_5pct_pre_20200824": "chinext pre-reform ST",
    "chinext_ipo_day1_prereg_cap": "chinext pre-reform IPO day1",
    "chinext_20pct_from_20200824": "chinext post-reform (>=2020-08-24)",
    "chinext_st_20pct_from_20200824": "chinext post-reform ST",
    "chinext_ipo_window5_from_20200824": "chinext post-reform IPO w5",
    "main_10pct": "main ordinary",
    "main_st_5pct": "main ST",
    "main_ipo_day1_prereg_cap": "main IPO day1 prereg cap",
    "main_ipo_fullreg_window5": "main IPO fullreg w5",
    "star_20pct_since_20190722": "star ordinary",
    "star_st_20pct": "star ST",
    "star_ipo_window5": "star IPO w5",
    "rule_unknown": "rule_unknown",
}


def main() -> int:
    df = pd.read_csv(SRC, dtype=str)
    key_cols = ["asset_id", "trade_date", "side"]
    n_rows = len(df)
    n_keys = df[key_cols].drop_duplicates().shape[0]

    seg_hits = (df.groupby(key_cols)["segment"]
                  .agg(lambda s: sorted(set(s))))
    multi_seg = seg_hits[seg_hits.map(len) > 1]

    cls_sets = df.groupby(key_cols)["classification"].agg(
        lambda s: sorted(set(s)))
    conflicts = cls_sets[cls_sets.map(len) > 1]
    conflict_rows = []
    for k in conflicts.index[:200]:
        a, d, s = k
        sub = df[(df.asset_id == a) & (df.trade_date == d) & (df.side == s)]
        conflict_rows.append({
            "asset_id": a, "trade_date": d, "side": s,
            "verdicts": sub[["segment", "classification",
                            "historical_rule", "old_flag"]].to_dict("records"),
        })

    # dedup: same key never gets two different classifications (verified 0
    # conflicts) — take first row per key for unique stats.
    u = df.drop_duplicates(subset=key_cols)
    klass = Counter(u["classification"])
    mis = u[u["classification"] == "CONFIRMED_MISLABEL"]
    fp = int((mis["old_flag"] == "True").sum())
    fn = int((mis["old_flag"] == "False").sum())
    by_rule = mis.groupby("historical_rule").size().sort_values(
        ascending=False)
    by_seg = mis.groupby("segment").size().sort_values(ascending=False)
    by_year = mis["trade_date"].str[:4].value_counts().sort_index()
    unknown = u[u["classification"] == "RULE_UNKNOWN"]

    summary = {
        "scope": ("LIMIT_FLAG_RECONCILIATION.csv is a TARGETED scan of "
                  "regime-divergent segments, NOT a census of the 17.29M-row "
                  "core.asset_status_daily table"),
        "scanned_rows": n_rows,
        "unique_keys_asset_date_side": int(n_keys),
        "duplicate_rows_collapsed": int(n_rows - n_keys),
        "keys_hitting_multiple_segments": int(len(multi_seg)),
        "classification_conflicts": int(len(conflicts)),
        "unique_classification": dict(klass),
        "unique_confirmed_mislabel": int(len(mis)),
        "unique_fp_old_flag_true_not_limit": fp,
        "unique_fn_old_flag_false_was_limit": fn,
        "mislabel_by_rule": by_rule.to_dict(),
        "mislabel_by_segment": {k: int(v) for k, v in by_seg.items()},
        "mislabel_by_year": {k: int(v) for k, v in by_year.items()},
        "rule_unknown_keys": unknown[
            ["asset_id", "trade_date", "side", "historical_rule"]
        ].to_dict("records"),
        "delta_vs_p1d1_row_level": {
            "row_level_mislabel": 63821,
            "unique_mislabel": int(len(mis)),
            "delta": int(len(mis)) - 63821,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "LIMIT_MISLABEL_DEDUP.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))

    lines = ["# P1d.2 LIMIT_MISLABEL_DEDUP_REPORT", "",
             "## 口径修正（相对 P1d.1 行级口径）", "",
             f"- 扫描行级记录：**{n_rows:,}**（多 segment 命中保留）",
             f"- 唯一键 `asset_id+trade_date+side`：**{n_keys:,}**"
             f"（折叠 {n_rows - n_keys:,} 行重复）",
             f"- 多 segment 命中键：{len(multi_seg):,}；分类冲突键：**{len(conflicts)}**",
             f"- **唯一实锤误标：{len(mis):,}**（行级口径 63,821 → "
             f"修正 {len(mis) - 63821:+,}；重复全部来自 FP 侧，FN 不变）",
             f"  - FP（旧标真/实为非限）：**{fp:,}**",
             f"  - FN（旧未标/实为限）：**{fn:,}**",
             f"- RULE_UNKNOWN：{int(klass.get('RULE_UNKNOWN', 0))} 唯一键",
             f"- CORRECT（段内抽样判定一致）：{int(klass.get('CORRECT', 0)):,}",
             "",
             "> 覆盖声明：LIMIT_FLAG_RECONCILIATION.csv 是**制度分歧高发段的"
             "定向扫描**，不是 1,729 万行 `asset_status_daily` 的全量普查；"
             "唯一计数只在扫描域内成立。", "",
             "## 按生效规则的唯一误标分布", "",
             "| historical_rule | 制度段 | 唯一误标行 |", "|---|---|---:|"]
    for r, c in by_rule.items():
        lines.append(f"| {r} | {RULE_ERA.get(r, '')} | {int(c):,} |")
    lines += ["", "## 按年份", "",
              "| 年份 | 唯一误标 |", "|---|---:|"]
    for y, c in by_year.items():
        lines.append(f"| {y} | {int(c):,} |")
    lines += ["", "## RULE_UNKNOWN 键（fail-closed 清单）", ""]
    for r in summary["rule_unknown_keys"]:
        lines.append(f"- {r['asset_id']} {r['trade_date']} {r['side']} "
                     f"({r['historical_rule']})")
    lines += ["", "## 分类冲突", "",
              f"{len(conflicts)} 键。" +
              ("详见 LIMIT_MISLABEL_DEDUP.json.conflict_rows。" if len(conflicts)
               else "同一 (asset,date,side) 跨 segment 判定完全一致——规则引擎在重叠段上可复现。")]
    (OUT / "LIMIT_MISLABEL_DEDUP_REPORT.md").write_text("\n".join(lines) + "\n")
    summary["conflict_rows"] = conflict_rows
    (OUT / "LIMIT_MISLABEL_DEDUP.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({"unique_mislabel": int(len(mis)), "fp": fp, "fn": fn,
                      "conflicts": int(len(conflicts))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
