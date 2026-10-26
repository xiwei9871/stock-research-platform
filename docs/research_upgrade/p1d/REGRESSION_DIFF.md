# REGRESSION_DIFF — 存储涨跌停标志 vs 历史生效规则

只读对照：`core.asset_status_daily.is_limit_up/is_limit_down`（构建时用**静态现行板块阈值**：ST 4.8 / BJ 29.8 / STAR+ChiNext 19.8 / 其他 9.8）与 `stock_research.tradeability.LIMIT_RULES`（按生效日期解析的历史规则）之间的分歧。

数据源：`scripts/p1d_tradeability_audit.py` → `tradeability_edge_cases.json.disagreement_scans`（2026-10-25 实跑）。

## 分歧汇总

| 扫描 | 存量分歧行数 | 含义 |
|---|---:|---|
| `chinext_pre_20200824_pct_9.9_19.8_stored_not_limit_up` | **28,205** | 2020-08-24 前创业板实际适用 ±10%，这批 pct_chg∈[9.9,19.8) 的收盘**当时真实涨停**，存储标志却是 `is_limit_up=false`——回测在该窗口会把涨停日误判为可买入 |
| `ipo_no_limit_window_stored_limit_up` | **1,305** | STAR(2019-07-22后)/ChiNext(2020-08-24后)/主板(2023-04-10后) 新股前5交易日无涨跌幅窗口内，存储 `is_limit_up=true`——当时根本无涨跌幅上限，属误标（且该批 pct_chg 常达 +100~800%） |
| `st_on_20pct_board_pct_5_19.8_stored_not_limit` | 0 | 创业板/科创板 ST 股按板块 ±20% 制度，存储层未出现分歧（ST 阈值 4.8 反而更保守，方向一致） |

## 方向性结论

1. **创业板 2020-08-24 制度变更是最大系统性缺口**：任何使用该历史窗口 is_limit 标志的回测，涨停可买判定约偏宽 28k 个资产-日。
2. **IPO 无涨跌幅窗口被反向误标**：1,305 行"涨停"其实无上限。新股前5日回测不能用普通 limit 标志。
3. **存储标志不重写**——P1d 要求只读。`tradeability_at` 输出 `stored_flag_disagrees` + `limit_rule_id`，下游回测资格判定应以**生效规则重算结果**为准，存储标志仅作参考。
4. ST 维度方向一致（4.8 阈值对 20% 板块偏严），未构成新增风险。

## 修复建议（P2 范围，未执行）

`build_asset_status_daily` 的 `limit_threshold_sql` 改为按 `trade_date` 查 `LIMIT_RULES` 等价 SQL（board × effective_date），并对 IPO 窗口（`listing_age<=5` 且板块注册制后）输出 `is_limit_*=false + limit_regime=no_limit_window`。属后续授权工作项。
