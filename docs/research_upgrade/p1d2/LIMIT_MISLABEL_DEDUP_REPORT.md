# P1d.2 LIMIT_MISLABEL_DEDUP_REPORT

## 口径修正（相对 P1d.1 行级口径）

- 扫描行级记录：**162,119**（多 segment 命中保留）
- 唯一键 `asset_id+trade_date+side`：**161,200**（折叠 919 行重复）
- 多 segment 命中键：911；分类冲突键：**0**
- **唯一实锤误标：62,937**（行级口径 63,821 → 修正 -884；重复全部来自 FP 侧，FN 不变）
  - FP（旧标真/实为非限）：**19,198**
  - FN（旧未标/实为限）：**43,739**
- RULE_UNKNOWN：8 唯一键
- CORRECT（段内抽样判定一致）：98,255

> 覆盖声明：LIMIT_FLAG_RECONCILIATION.csv 是**制度分歧高发段的定向扫描**，不是 1,729 万行 `asset_status_daily` 的全量普查；唯一计数只在扫描域内成立。

## 按生效规则的唯一误标分布

| historical_rule | 制度段 | 唯一误标行 |
|---|---|---:|
| chinext_10pct_pre_20200824 | chinext pre-reform (<2020-08-24) | 38,618 |
| pre_19961216_no_limit | pre-limit era (<1996-12-16) | 8,227 |
| main_st_5pct | main ST | 5,550 |
| chinext_ipo_day1_prereg_cap | chinext pre-reform IPO day1 | 3,669 |
| chinext_st_20pct_from_20200824 | chinext post-reform ST | 3,052 |
| main_10pct | main ordinary | 1,676 |
| chinext_ipo_window5_from_20200824 | chinext post-reform IPO w5 | 625 |
| star_ipo_window5 | star IPO w5 | 603 |
| star_st_20pct | star ST | 267 |
| main_ipo_fullreg_window5 | main IPO fullreg w5 | 220 |
| chinext_20pct_from_20200824 | chinext post-reform (>=2020-08-24) | 196 |
| star_20pct_since_20190722 | star ordinary | 125 |
| main_ipo_day1_prereg_cap | main IPO day1 prereg cap | 109 |

## 按年份

| 年份 | 唯一误标 |
|---|---:|
| 1990 | 2 |
| 1991 | 123 |
| 1992 | 453 |
| 1993 | 870 |
| 1994 | 3,507 |
| 1995 | 1,164 |
| 1996 | 2,150 |
| 1997 | 219 |
| 1998 | 142 |
| 1999 | 155 |
| 2000 | 230 |
| 2001 | 136 |
| 2002 | 148 |
| 2003 | 136 |
| 2004 | 239 |
| 2005 | 401 |
| 2006 | 305 |
| 2007 | 509 |
| 2008 | 443 |
| 2009 | 423 |
| 2010 | 777 |
| 2011 | 794 |
| 2012 | 1,213 |
| 2013 | 1,820 |
| 2014 | 1,899 |
| 2015 | 13,529 |
| 2016 | 5,267 |
| 2017 | 3,806 |
| 2018 | 4,779 |
| 2019 | 5,219 |
| 2020 | 5,526 |
| 2021 | 1,016 |
| 2022 | 739 |
| 2023 | 558 |
| 2024 | 1,588 |
| 2025 | 1,424 |
| 2026 | 1,228 |

## RULE_UNKNOWN 键（fail-closed 清单）

- CN:SH:600653 1990-12-19 buy (rule_unknown)
- CN:SH:600653 1990-12-19 sell (rule_unknown)
- CN:SH:600651 1990-12-19 buy (rule_unknown)
- CN:SH:600651 1990-12-19 sell (rule_unknown)
- CN:SH:600602 1990-12-19 buy (rule_unknown)
- CN:SH:600602 1990-12-19 sell (rule_unknown)
- CN:SH:600601 1990-12-19 buy (rule_unknown)
- CN:SH:600601 1990-12-19 sell (rule_unknown)

## 分类冲突

0 键。同一 (asset,date,side) 跨 segment 判定完全一致——规则引擎在重叠段上可复现。
