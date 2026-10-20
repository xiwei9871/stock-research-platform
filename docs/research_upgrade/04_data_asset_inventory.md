# DATA-01 全平台数据资产盘点（只读，2026-10-21）

口径说明：行数为 `pg_class.reltuples` 估算；时间范围为真实 min/max。
**完整性（历史应有 vs 实有）、时效性（最新日期）、可解析性（可用层）分开统计，不合并为单一 READY 指标。**
原始明细：`outputs/research/data_asset_inventory_20261021.jsonl`

## 一、行情数据

| 数据集 | 存储 | 覆盖范围 | 行数(估) | 状态 |
|---|---|---|---|---|
| 日线 | `public.market_daily_bar` | 1990-12-19 → **2026-10-20**；近日 ~5,190 股/日 | 50.9M | ✅ 完整且新鲜 |
| 指数日线 | `market.index_daily_bar` | → 2026-10-19；**仅 8 只指数** | 36k | ⚠️ 指数覆盖极窄 |
| 行业日线 | `market.industry_daily_bar` | → 2026-10-19 | 844k | ✅ |
| 概念日线 | `market.concept_daily_bar` | **2024-01-02 起** → 10-19 | 243k | ⚠️ 历史仅 2.8 年 |
| 5分钟线 | `market.stock_minute_bar`(分区) | 2020-01-02 → **2026-10-20**，qfq+raw 双份 | 735.7M | ✅ 新鲜；⚠️ 历史仅 2020 起、仅 5min freq |
| 开盘竞价 | `market.stock_auction_bar` | tdx 2018-02-14→**10-20**(7.04M) + tushare 2009-01-05→2026-06-09(9.27M 冻结) | 14.96M | ✅ TDX 已恢复；tushare 按计划冻结 |
| 竞价分钟 | `market.stock_auction_minute_bar` | 2026-06-10 → 10-20 (EM) | 38k | ⚠️ 仅 4 个月 |
| 竞价明细 | `market.stock_auction_detail` | **仅 2026-06-09 一天 58 行** | 58 | ❌ 基本空 |
| 开盘快照 | `market.stock_open_auction_snapshot` | 2026-06-29 → 10-20 | 565k | ⚠️ 仅 ~4 个月 |
| 复权因子 | `market.adjustment_factor` | 1990 → **2026-08-27** | 16.7M | ❌ **停更 ~2 个月** |
| 公司行动 | `market.corporate_action` | 1990 → **2026-07-27** | 15.6M | ❌ **停更 ~3 个月** |
| 交易日历 | `market.trading_calendar` | → 2027-02 | 17.8k | ✅ |

## 二、财务与公告

| 数据集 | 覆盖 | 状态 |
|---|---|---|
| 利润表 `finance.income_statement` | 1988 → **2026-03-31** | ❌ **缺 2026Q2**（balance/cash 已到 06-30，income 缺期不对称） |
| 资产负债 `balance_sheet` / 现金流 `cash_flow` | → 2026-06-30 | ✅ Q2 已到 |
| 财务指标 `indicator_quarter` | 2007 → 2026-03-31 | ⚠️ 落后一期 |
| 主营构成 `main_business_composition` | **2022-12-31 起** → 2026-03-31 | ⚠️ 历史仅 3 年 |
| 股本变动 `share_capital_event` | 2007 → **2026-06-08** | ❌ 停更 ~4 个月 |
| 业绩快报 `earnings_express` | **仅 1,085 行**，2025-03-31 → 2026-09-30 | ❌ 历史极浅 |
| 业绩预告 `earnings_forecast` | 23,391 行，2025-03-31 起 | ❌ 历史仅 ~1.5 年 |
| 机构调研 `institution_survey` | 2025-01-16 → **10-20** | ✅ 新鲜；⚠️ 历史仅 ~1.8 年 |
| 股东减持 `shareholder_trade` | 2011 → **2026-06-04** | ❌ 停更 ~4.5 个月 |
| 回购 `stock_repurchase` | 2025 → 10-20 | ✅ |
| 股东户数 `shareholder_count` | 2025-01 → **2026-06-02** | ❌ 停更 |
| 十大股东/流通股东 `top10_*` | 2025-03-31 起 → 2026-03-31 | ⚠️ 仅 4 期、落后 1 期 |

## 三、新闻、研报与证据

| 数据集 | 覆盖 | 状态 |
|---|---|---|
| 新闻源 `news_event_source` | 2026-06-12 → 10-20 (19:03) | ✅ 新鲜；⚠️ 历史仅 4 个月；active=0 待查 |
| 新闻提及 `news_event_mention` | 6-12 → 10-20，418 行 | ⚠️ 提及稀疏 |
| 新闻特征 `news_feature_daily` | 6-18 → 10-19 | ✅ |
| 研报源 `stock_report_source` | 57k 行，2017 → 10-13 | ⚠️ 近一周无新入库；**293 组 uuid 重复/595 行** |
| 研报事件 `stock_report_event` | 58k 行 | ⚠️ 事件数 ≈ 源数（重复同步放大）；分层：目录>PDF>解析>证据 |
| 研报特征 `stock_report_feature_daily` | 2025-01-02 → **2026-07-23** | ❌ **停更 3 个月** |
| 研报分层（yanbaoke 子集） | catalog 2,174 / local_uri 2,067 / 可解析 1,696 | ⚠️ ~478 有目录无 PDF 或不可解析 |

## 四、因子与衍生数据

| 数据集 | 覆盖 | 状态 |
|---|---|---|
| 技术特征 `stock_technical_features_daily` | 1990 → 10-19，33.9M | ✅ |
| 因子库 `factor_daily` | 1991 → 10-19，587.5M | ✅ |
| 股票打分 `stock_score_daily` | 2023-01-03 → 10-19，8.3M | ✅ |
| **盘中特征 `stock_intraday_features_daily`** | 2025-01-02 → **2026-08-03** | ❌ **停更 ~2.5 个月**（已知未恢复项） |
| 行业盘中特征 | 同上 → 2026-08-03 | ❌ 同上 |
| staging intraday | 仅 8-04/8-05 两天 | ⚠️ 恢复尝试残留 |
| LHB 榜 `lhb_top_*_daily` | 2024-01-10 → 10-19 | ✅ |
| LHB 特征 | 同上 | ✅ |
| 市场情绪 `market_emotion_state_daily` | 6-23 → 10-19，79 日 | ✅（regime 用） |

## 五、研究资产与主数据

| 数据集 | 覆盖 | 状态 |
|---|---|---|
| 证券主档 `core.asset_master` | 5,540 只，上市日至 2026-07-10 | ✅ |
| 证券状态 `asset_status_daily` | 1990 → 10-19，17.1M | ✅ |
| 生命周期事件 `asset_lifecycle_event` | → **2026-04-30** | ❌ 停更 ~6 个月（退市/更名事件可能漏） |
| 行业成员 `industry_membership` | 1990 → 2026-07-31 | ⚠️ 有效性窗口至 7-31 |
| 概念成员 `concept_membership` | **仅 2026-07-09→08-27** | ❌ 历史窗口仅 7 周 |
| 指数成分 `index_constituent` | 2006 → start_date ≤2026-07-31 | ⚠️ 待核验当前成分有效性 |
| 卡脖子评审池 | 359 股（2026-09-22 快照） | ✅ |
| 主题公司映射 | 236 映射，活跃过滤后并入优先池 | ✅ |
| `theme_research_theme` | **25 行**（est 曾误报 0） | ✅ 小但非空 |

## 六、运维台账

- `ingest.backfill_task` 2,653 tasks / 3 runs（TDX 回填账本已验收）
- `ops.daily_pipeline_status` → 10-19 ✅；`ops.daily_job_run` 止于 6-17（被 status 取代）
- `raw_baostock.daily_bar_payload` 31M → 07-31（原始载荷冻结点，前向走正式表）

---

## P0/P1/P2 缺口优先级

### P0（阻塞研究/策略正确性）
1. **income_statement 缺 2026Q2** — balance/cash 已到 06-30，income 仅到 03-31 → Q2 财务分析不对称，护城河/卡脖子财务证据失真
2. **stock_intraday_features_daily 停更 ~2.5 个月**（→08-03）— 盘中策略与 Intraday 恢复的直接阻塞项（已有独立恢复计划）
3. **adjustment_factor / corporate_action 停更 2-3 个月**（→08-27 / →07-27）— 复权价与分红送转失真，影响全量回测与 qfq 计算
4. **asset_lifecycle_event 停更 ~6 个月** — 退市/更名漏记会污染证券池 PIT

### P1（显著但非阻塞）
5. **stock_report_feature_daily 停更 3 个月**（→07-23）— 研报特征不再刷新，报告驱动信号失效
6. **shareholder_trade / share_capital_event / shareholder_count 停更 3-5 个月** — 减持与股本证据滞后
7. **top10 持有人数据落后一期**（→2026-03-31）且历史仅 4 期
8. **earnings_express/forecast 历史仅 ~1.5 年** — 事件回测无深度历史
9. **concept_membership 仅 7 周历史** — 概念股归属无法回溯
10. **stock_auction_detail 仅 1 天 58 行** — 明细层事实性缺失
11. **index_daily_bar 仅 8 只指数** — 指数覆盖过窄（申万/中证行业指数缺）
12. **研报源近一周无新入库** — 与 A2 周补机制联动解决

### P2（改善性）
13. 分钟线仅 5min freq、历史起自 2020；1min/更早历史属新增资产
14. EM 竞价分钟/开盘快照仅 ~4 个月历史
15. institution_survey/stock_repurchase 历史浅（~1.8 年）
16. 新闻历史仅 4 个月、mention 稀疏
17. `raw_baostock.finance_payload` / `raw_akshare.enrichment_payload` 空表（占位未用）

## 建议补全节奏（详见 A3 运营计划）
- **每日**：日线/指数/行业/5min/TDX 竞价(已恢复)/技术因子/打分/LHB/新闻/复盘特征
- **事件驱动**：公告类（调研✅、回购✅、减持✖、快报/预告✖）
- **定期(季)**：财报三张表、指标、十大股东（income Q2 需补采）
- **每周**：研报客 25 篇上限（DATA-02）
- **低频**：主数据/成员关系校验（lifecycle、concept_membership 当前是缺口）
