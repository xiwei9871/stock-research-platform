# Stock Research Platform 全量梳理

生成日期：2026-07-06  
仓库：`/Users/xiwei/stock_research`  
用途：给外部专家快速理解当前平台现状、边界、数据资产、功能模块和策略研究方向。

## 1. 一句话定位

这是一个 A 股中低频研究与人工复核平台，不是自动交易系统。平台围绕 PostgreSQL 研究库、因子打分、TopN/观察池、策略回测、每日复盘、研报/新闻证据、前端工作台、人工决策记录和影子生命周期，输出“研究结论、证据、候选池、风险提示和复核材料”，最终交易动作仍由人决策。

当前仓库 README 将 P0-P19 定义为已闭合的平台基础：数据与每日操作、只读 Dashboard、Operator 决策闭环、Outcome 分析、Experiment 沙盒、Shadow watchlist/P17/P18 跟踪与复核。P19 之后的 alpha191、mid-trend、strong-winner、stock-report/docling 等属于持续策略研究和数据增强轨道。

## 2. 当前代码与环境状态

- Python 包：`stock-research`，入口 `stock-research = stock_research.cli:main`。
- Python 版本：`>=3.11`。
- 后端主要依赖：`akshare`、`baostock`、`pandas`、`psycopg[binary]`、`pypdf`、`requests`；Dashboard API 可选 `fastapi`、`uvicorn`。
- 前端：`dashboard/`，Vite + React 19 + TypeScript + ECharts + lightweight-charts + lucide-react。
- 数据库连接：PostgreSQL service 模式，默认 `stock_research`，另有 `stock_hfq`、`stock_qfq`。
- 当前 worktree 已有未提交改动，集中在 minute backfill、dashboard backtests、strategy EOD、data-to-brief/docling 模块和对应测试；本次梳理只读未修改这些业务文件。

## 3. 顶层目录

- `src/stock_research/`：Python 后端、CLI、数据/因子/策略/报告/API 模块。
- `dashboard/`：唯一 canonical React SPA 前端。
- `tests/`：后端、脚本、Dashboard API、策略、数据质量等 pytest。
- `dashboard/tests/`：Vitest + Playwright 前端测试。
- `docs/`：目标架构、P0-P19 文档、runbook、设计规格、研究总结。
- `scripts/`：cron、watchdog、批量补数、策略/数据实验脚本。
- `deploy/`：SQL 部署脚本和 launchd plist。
- `reports/`：日常 TopN、组合、报告包等用户可读产物。
- `outputs/research/`：策略、诊断、回测、研报、新闻、docling 等研究产物。
- `config/`：机构名单、研报优先级等配置输入。
- `data/seed/`：dragon case 种子数据。
- `logs/`：全历史补数、watchdog、quota 等日志。

## 4. 系统分层

当前目标架构分 13 层：

1. Data Layer：原始和标准化数据入库。
2. Data Quality Layer：覆盖率、异常、PIT 约束巡检。
3. Universe Layer：可研究股票池、交易状态、ST/停牌/板块过滤。
4. Factor Layer：因子计算、注册、落库、lineage。
5. Factor Validation Layer：IC、RankIC、分组收益、换手、暴露、门禁。
6. Backtest Layer：TopN、Retention、Portfolio、策略验证。
7. Stock Screener Layer：全市场 TopN、候选池变化、风险剔除。
8. Regime Layer：市场状态和行业主线。
9. Watchlist Layer：人工精选池和短线观察池。
10. AI Agent Research Layer：证据驱动的投研助理层。
11. Report Layer：Markdown/CSV/JSON 报告包。
12. OpenClaw / Feishu Integration Layer：报告投递和告警。
13. Future Semi-Auto Trading Layer：仅预留建议单，不接实盘自动下单。

## 5. 数据库现状

数据库按 schema 分层。当前 catalog 查询结果：

| Schema | 表数量 | 主要内容 |
| --- | ---: | --- |
| `market` | 53 | 日线、分钟线分区、指数、行业/概念、竞价、龙虎榜、交易日历 |
| `ops` | 38 | 每日 pipeline 状态、data manifest、review queue、operator/shadow read models |
| `research` | 9 | 研报、新闻、研报特征、市场情绪状态 |
| `factor` | 8 | 因子长表、股票得分、技术/盘中特征、LHB 特征、因子评价/审批 |
| `core` | 6 | 股票主数据、状态、生命周期、行业/概念归属 |
| `finance` | 6 | 三张表、财务指标、股本、主营构成 |
| `event` | 5 | 股东交易、回购、调研、业绩预告/快报 |
| `staging` | 5 | Baostock 分钟、Tushare 竞价、Eastmoney、XTick 暂存 |
| `backtest` | 4 | 策略回测 run/equity/position/trade |
| `ingest` | 4 | batch/backfill 控制面 |
| `fundamental` | 3 | 股东数、前十大股东、前十大流通股东 |
| `raw_baostock` | 3 | Baostock 原始日线/财务/行业 payload |
| `simulation` | 2 | 虚拟组合状态和持仓 |
| `watchlist` | 2 | 观察池条目和每日信号 |
| `raw_akshare` | 2 | AkShare 财务和 enrichment 原始 payload |

当前没有业务 SQL view，主要以表和 read model 承载。

关键表规模和覆盖范围：

| 数据集 | 行数/规模 | 日期范围 |
| --- | ---: | --- |
| `core.asset_master` | 5,209 | 当前 A 股主数据规模 |
| `market_daily_bar` | 35,680,350 | 1990-12-19 至 2026-07-03 |
| `market.stock_minute_bar` | 315,345,414 | 2020-01-02 至 2026-07-03 |
| `factor.factor_daily` | 357,910,930 | 1991-06-24 至 2026-07-03 |
| `factor.stock_score_daily` | 8,369,992 | 2023-01-03 至 2026-07-03 |
| `watchlist.watchlist_daily_signal` | 927 | 2026-06-18 至 2026-07-03 |
| `research.stock_report_source` | 58,300 | 研报来源元数据 |
| `research.news_event_source` | 461 | 新闻事件来源 |
| `ops.operator_decision_event` | 2 | 人工决策事件样本 |

`market.stock_minute_bar` 已按月分区，存在 2024-2026 月度分区以及 default/unpartitioned backup。2024 年单月分区体量大约 2.2GB-3.2GB 级别，主键和索引也较大。

## 6. 当前运行状态快照

最新业务数据日期为 2026-07-03。最近 `ops.daily_pipeline_status`：

- `2026-07-03`：`DEGRADED_READY`，`daily_status=partial_success`，`minute5_status=success`，`deps_status=success`，`market_monitor_status=success`。
- `2026-07-02`：`DEGRADED_READY`，结构同上。
- `2026-07-01`：`DEGRADED_READY`，`deps_status=skipped`，`market_monitor_status=skipped`。

最新 `ops.data_run_manifest` 显示 `2026-07-03` 的 EOD 发布链路已记录成功：

- `daily_bars`：5,190 行
- `technical_features`：5,190 行
- `score_topn`：5,190 行
- `lhb_features`：141 行
- `strategy_lhb_shortline`：5 行
- `strategy_mid_trend`：1 行
- `tech_bottleneck_candidates`：13,602 行
- `strategy_tech_bottleneck`：5 行
- `review_queue_strategy_manifest`：11 行
- `news` / `news_features` / `news_enrichment` / `generated_reports` / `review_evidence_snapshots` 均成功

`ops.strategy_daily_eod_status` 最新：

- `2026-07-03`：整体 success；LHB、Mid Trend、Tech Bottleneck 均 success；review rows 5。

注意：平台可用状态是 degraded-ready，而不是完全无缺口 ready，主要因为日线 pipeline 是 partial_success。

## 7. 因子和评分

主要代码：

- `factor_config.py`、`factor_pipeline.py`、`factor_store.py`
- `factors/alpha101.py`
- `factors/gtja191.py`
- `factors/qlib_alpha.py`
- `factors/trend.py`
- `factors/momentum.py`
- `factors/volume_price.py`
- `factors/sector.py`
- `factors/risk.py`
- `factors/value.py`
- `factors/growth.py`
- `factors/quality.py`
- `scoring/`
- `factor_eval/`

因子评价模块包括：

- `ic.py`：IC / RankIC
- `quantile_return.py`：分组收益、Top-Bottom
- `turnover.py`：TopN 换手
- `exposure.py`：行业/市值暴露
- `multi_horizon.py`、`period.py`、`segment.py`
- `gate.py`：因子门禁
- `validation_review.py`：评价复核

当前主要 score version：

| Score version | 日期范围 | 行数 | 股票数 |
| --- | --- | ---: | ---: |
| `manual_v1` | 2024-01-02 至 2026-07-03 | 3,085,550 | 5,209 |
| `flow_full_20240527_20260508_v1` | 2024-05-27 至 2026-05-08 | 2,415,261 | 5,201 |
| `manual_v1_research_2023` | 2023-01-03 至 2023-12-29 | 1,185,601 | 5,009 |
| `flow_full_20240527_20250508_v1` | 2024-05-27 至 2025-05-08 | 1,167,006 | 5,119 |
| `flow_smoke_100d_v1` | 2024-07-24 至 2024-12-19 | 506,215 | 5,081 |

因子审批门禁当前为 2 approved、46 rejected。已批准：

- `gtja191_amount_momentum_5_10`
- `qlib_ret_5`

大量基本面/估值因子当前 rejected，原因主要是 `missing_factor_data`，部分价量/行业因子因 `mean_ic_below_threshold` 或 `icir_below_threshold` 被拒。

## 8. 后端和 CLI

`src/stock_research/cli.py` 是统一命令入口，覆盖面很广，主要命令族包括：

- Schema / 数据基础：`apply-schema`、`apply-research-schema`、`sync-assets`、`sync-core-assets`、`sync-stock-chinese-names`
- Pipeline：`daily-pipeline`、`intraday-pipeline`、`run-daily-factor-pipeline`、`run-stock-daily-data-pipeline`、`run-daily-incremental`
- 数据质量：`data-audit`、`data-quality`、`finance-audit`、`research-preflight`、`daily-health`
- 维度/行情：交易日历、asset lifecycle、asset status、复权因子、corporate actions、industry/concept/index bars、minute bars、auction bars
- Ingest/backfill 控制面：create/claim/status/reset/mark backfill task，ingest jobs loop/status
- 特征/标签：`features`、`labels`、technical/intraday feature daily/backfill/gap check
- 因子：`build-factor-daily`、`score-factor-daily`、`show-top-scores`、`eval-factor`、`evaluate-factor-gate`、`evaluate-factor-gate-batch`
- 回测/模拟：`backtest-top20`、`portfolio-backtest`、`simulate-portfolio`、`retention-backtest`
- 报告投递：local、OpenClaw export/send、Feishu dry-run/send
- Dashboard：`dashboard-api`
- P2-P18 operator/shadow 生命周期：artifact rollup、operator journal、outcome review/analytics、experiment proposal/replay、shadow watchlist/outcomes/analytics/review decisions/follow-up queue/resolution/imports
- 策略研究：mid-trend、LHB shortline、dragon、industry regime、watchlist diagnostics、strong-winner、alpha191、tech bottleneck、stock report/yanbaoke/hibor/docling

## 9. Dashboard API

后端 API 位于 `src/stock_research/dashboard/app.py`，FastAPI 应用由 `create_app()` 构建。主要 endpoint：

- 平台概览：`/api/dashboard/overview`、`/api/platform/summary`、`/api/platform/readiness`、`/api/platform/display-date`
- 数据与运维：`/api/data/status`、`/api/ops/snapshot`、`/api/ops/stages`、`/api/public/snapshot`、`/api/intraday/status`
- 市场监控：`/api/market-monitor/eod`、overview、sector heatmap、fund flow、sector detail
- 复盘：`/api/review-queue`、daily review lite、evidence digest、strategy score audit、snapshots
- 新闻和研报：`/api/public-news`、refresh/status、`/api/research-reports/*`、`/api/assets/{asset_id}/research-reports`
- 个股：search、detail、bars、minute-bars、scores、profile、signals、decisions、outcomes、news
- Operator 写入口：`POST /api/operator-decisions`、`PATCH /api/operator-decisions/{event_id}`
- Outcome / experiment / shadow：outcome analytics、experiment proposals/replay、shadow watchlist/outcomes/analytics/review decisions/follow-up queue/resolution
- TopN/watchlist/reports：`/api/topn`、`/api/watchlists/{watchlist_id}`、`/api/reports`
- 策略和回测：strategy catalog、backtest strategies/jobs/run/fresh/replay、factor library/score preview、strategy-validation runs/signals/trades/positions/metrics/artifacts/replay

## 10. 前端

Canonical frontend 是单一 React SPA：

`dashboard/index.html -> dashboard/src/main.tsx -> dashboard/src/App.tsx -> dashboard/src/components/AppShell.tsx`

明确不再维护独立 public snapshot 页面或第二前端入口。

主要 workspace：

- 首页 Cockpit
- Review Queue
- Daily Review
- Market Monitor
- News
- Research Reports
- Stock Workspace
- Watchlist
- Tech Bottleneck Watchlist Review
- Factor Lab
- Strategy Lab
- Generated Reports

前端 API client：`dashboard/src/api/client.ts`，覆盖 overview、market monitor、public news、research reports、evidence digest、review queue、daily review、watchlist、asset bars/profile/news、operator decisions、outcomes、shadow lifecycle、strategy validation、platform readiness、factor lab、backtest lab 等。

前端测试覆盖：

- AppShell、HomeCockpit、GlobalSearch
- MarketMonitor、News、ResearchReports、StockWorkspace、Watchlist
- FactorLab、StrategyLab、BacktestLab、StrategyValidation
- DailyReviewLite、ReviewQueue
- Tech Bottleneck route/workbench
- chart rendering、strategy markers、canonical frontend entry
- Playwright smoke 和 full-flow

## 11. 数据流水线

### Daily close pipeline

文档：`docs/daily-close-pipeline-runbook.md`

- 目标：收盘后更新 A 股数据，不依赖 Baostock。
- Tushare 是全市场 raw daily 主源。
- AkShare 是缺失 `(ts_code, adjust_type)` 的 fallback，包括 `qfq`、`hfq`。
- 默认日线 adjust types：`raw,qfq,hfq`。
- 5 分钟数据有独立 stage。
- 状态表：`ops.daily_pipeline_job`、`ops.daily_pipeline_quality`、`ops.daily_pipeline_failed_symbol`、`ops.daily_pipeline_status`。

### Intraday pipeline

文档：`docs/intraday-pipeline-runbook.md`

- 用于 T+1 短线决策 universe 和 5 分钟轮询。
- Universe 来自前一交易日 TopN、watchlist signals、当前虚拟持仓。
- 不拉全市场 5 分钟线，而是只拉 `ops.intraday_universe_member` 中的标的。
- Sentiment 用 AkShare Eastmoney A 股快照和涨跌停池。

### Daily factor pipeline

文档：`docs/daily-factor-pipeline-runbook.md`

典型顺序：

1. `apply-research-schema`
2. `labels`
3. `build-factor-daily`
4. `score-factor-daily --score-version manual_v1`
5. `show-top-scores`
6. 候选因子先经 `evaluate-factor-gate` 或 batch gate，再进入 scoring。

### EOD auto repair

README 描述的 repair 顺序：

1. base bars
2. features
3. scores/watchlists
4. market monitor
5. strategy EOD
6. presentation freshness

Baostock minute repair 被明确限制为单 worker。

## 12. 策略与算法模块

### Manual V1 TopN Rotation

- `manual_v1` 是主要股票打分版本。
- 用于 TopN baseline、Factor Lab、研究报表和部分 fallback。
- 在 Strategy Catalog 中是 diagnostic，不是正式组合策略。

### LHB Shortline Combo

文档：`docs/research/lhb_shortline_strategy_development_summary_20260609.md`

定位：龙虎榜短线资金/情绪事件策略，不是低风险价值策略。核心问题是 LHB 信号后能否继续跟随，以及情绪周期是否衰退。

数据层：

- 日度 LHB 特征
- 日 K 和涨停生命周期
- 5 分钟盘中 bars
- Tushare 开/收盘竞价 bars

当前方向：

- 高开本身不是直接否定。
- 用开盘竞价和早盘 5 分钟确认 followability。
- 用收盘竞价 + weak-open context 检测退潮。
- 退出遵守 A 股 T+1 和 5 分钟可交易约束。

Catalog 最新证据：LHB shortline v1.1 从 DB 基础表重算，默认市场仓位控制，Top5/20%/10bps 净值约 2.6069，最大回撤约 -5.32%。

### Mid Trend Combo

定位：中期趋势组合，每周调仓，Top5，限制单周替换数量，避免过度换仓。

核心输入：

- 趋势强度
- 20 日收益
- 成交活跃度
- 回撤控制
- 趋势延续质量
- 持仓保护

当前证据：2026 区间净值约 1.5599，最大回撤 -17.52%。

相关研究：

- `mid-trend-round2-optimize`：二轮优化，输出 baseline train/test、failure mode、candidate audit、report。
- `mid-trend-soft-ownership-optimize`：baseline-safe 实验，评估 `entry_soft_weight_v1`、`ownership_hold_v1`、`partial_exit_v1`、`combined_soft_ownership_v1`。

### Tech Bottleneck Combo

定位：在趋势候选股中寻找技术形态、成交确认、突破质量更强的股票，偏科技卡脖子/硬科技候选池。

核心输入：

- 技术瓶颈形态
- 20 日收益
- 成交量确认
- 收盘位置
- 回撤控制
- 趋势候选池
- 假突破过滤

当前证据：严格科技瓶颈池 + ST 剔除 + 每周 Top5 + 市场环境仓位控制，2026-01-01 至 2026-06-08 净值约 1.6007，最大回撤约 -8.30%。

前端有独立 `Tech Bottleneck Watchlist Review` route，但仍在 canonical AppShell 内。

### Watchlist Diagnostics

文档：`docs/watchlist-diagnostics-runbook.md`

目的：生成短线观察池诊断、must_watch 复核、滚动 effectiveness review，不是自动交易信号。

输入：

- `factor.stock_score_daily`
- `factor.factor_daily`
- `factor.stock_technical_features_daily`
- `market_daily_bar`
- Dragon / LHB 研究产物

输出：

- `watchlist_diagnostics_*_diagnostics_v1.csv`
- `watchlist_diagnostics_must_watch_*_diagnostics_v1.csv`
- `watchlist_diagnostics_*_diagnostics_v1.md`
- effectiveness detail/summary/report

### Dragon / Strong Winner / Alpha191

这些属于 P19 之后的策略研究或专题研究：

- Dragon case library：`dragon_case_library.py`、seed 数据、curated library、source backfill。
- Strong winner：miss analysis、taxonomy、capture gap、discovery pool、TopN attribution。
- Alpha191：pilot/expanded validation artifacts 已存在于 `outputs/research/`，但 README 仍将 alpha191 production integration 标为单独未来轨道。

## 13. 报告、研报、新闻和证据

### 报告产物

`reports/` 当前有 365 个文件，主要是 daily TopN、approved v1 TopN、组合回测报告等。

`outputs/research/` 当前有 5,234 个文件，包含：

- alpha191 pilot/expanded validation
- LHB daily watchlists
- dragon case artifacts
- watchlist diagnostics
- mid-trend research artifacts
- tech bottleneck artifacts
- strategy daily EOD outputs
- review evidence snapshots
- data-to-brief/docling outputs
- 各类 CSV/MD/JSON/JSONL/TXT

### 研报系统

表：

- `research.stock_report_source`
- `research.stock_report_event`
- `research.stock_report_manual_review`
- `research.stock_report_search_task`
- `research.stock_report_feature_daily`

当前 `research.stock_report_source` 约 58,300 行。Dashboard 提供研报列表、过滤、详情、PDF、本地 PDF fallback 和个股研报关联。

### 新闻系统

表：

- `research.news_event_source`
- `research.news_event_mention`
- `research.news_feature_daily`

Dashboard 提供 public news、refresh/status、资产新闻、质量评分、mention 映射、新闻特征。

### Evidence Digest / Review Queue

EOD 发布链会写 `review_evidence_snapshots` 和 `review_queue_strategy_manifest`，供首页、复盘队列、个股证据 hub 和策略复核使用。

## 14. Operator / Shadow 生命周期

P7-P18 完成的是人工复核和影子生命周期，不是生产 promotion。

主要 read models：

- `ops.operator_decision_event`
- `ops.operator_decision_outcome_run/event`
- `ops.operator_decision_outcome_analytics_run/group`
- `ops.operator_experiment_proposal_run/proposal`
- `ops.operator_experiment_replay_run/result`
- `ops.operator_shadow_watchlist_run/candidate`
- `ops.operator_shadow_watchlist_outcome_run/candidate`
- `ops.operator_shadow_watchlist_outcome_analytics_run/group`
- `ops.operator_shadow_analytics_review_run/group`
- `ops.operator_shadow_review_decision_run/group`
- `ops.operator_shadow_follow_up_run/item`
- `ops.operator_shadow_follow_up_resolution_run/item`

关键边界：

- shadow rows 不是生产批准。
- P18 resolution labels 只是复核标签。
- P17 queue 和 P18 resolution 是分离 read model，P18 不回写关闭 P17。
- 生产 watchlist promotion 需要未来单独 phase。

## 15. 部署和运维

部署目录：

- `deploy/daily_close_pipeline.sql`
- `deploy/intraday_pipeline.sql`
- `deploy/launchd/com.stockresearch.factor-gate-backfill-watchdog.plist`
- `deploy/launchd/com.stockresearch.minute-backfill-watchdog.plist`
- `deploy/launchd/com.stockresearch.technical-feature-backfill-watchdog.plist`

脚本目录有 126 个脚本，其中 105 个 Python、21 个 shell，覆盖：

- daily close pipeline cron
- platform ready build/check cron
- strategy daily EOD cron
- minute backfill watchdog
- technical feature / factor gate watchdog
- open auction collection
- stock report / Yanbaoke / Hibor backfill
- tech bottleneck candidate universe
- docling data-to-brief pilot/recovery/integration

## 16. 测试体系

后端测试覆盖：

- schema / migration safety
- data quality / data audit / finance audit
- factor store / factor eval / factor gate / alpha factors
- market data / minute data / intraday features
- backtest / portfolio / retention / constraints
- operator decision/outcome/experiment/shadow lifecycle
- dashboard API schemas/routes
- daily pipeline / strategy EOD / EOD auto repair
- LHB / mid-trend / tech bottleneck / watchlist / strong-winner / dragon
- report delivery Feishu/OpenClaw
- docling/data-to-brief modules

前端测试覆盖前述 Dashboard workspaces，并有 Playwright smoke/full-flow。

P19 final smoke 文档记录过：

- 后端 focused smoke：40 passed
- Dashboard Vitest：33 passed
- Dashboard build 成功
- Dashboard Playwright smoke：2 passed

本次梳理未重新跑完整测试，只做只读检索、catalog 查询和文档生成。

## 17. 明确安全边界

平台不做：

- 自动交易
- broker 接入
- 真实订单
- 账户/现金/持仓 mutation
- 实盘 execution state
- shadow 自动转生产
- P18 resolution 自动转生产审批

平台做：

- 数据采集、清洗、PIT 存储
- 因子计算和审批门禁
- 候选池和观察池
- 回测和策略验证
- 日常复盘和证据收集
- 人工决策记录和结果分析
- 影子生命周期研究
- 报告投递和只读 Dashboard

## 18. 主要缺口和风险点

1. `DEGRADED_READY` 是当前常态之一，日线数据常为 `partial_success`；专家讨论时应明确 degraded 的容忍阈值和修复 SLA。
2. `factor.factor_daily` 和 `market.stock_minute_bar` 规模很大，查询、VACUUM、分区维护、索引膨胀是核心运维风险。
3. 因子审批目前只有 2 个 approved，说明主评分体系仍然较保守，基本面因子数据质量/覆盖需要补强。
4. Strategy EOD 已能发布 LHB/MidTrend/TechBottleneck，但 official/live 与 experimental/replay 产物之间的边界要持续保持清晰。
5. Operator decision 当前样本很少，人工决策闭环的数据量还不足以形成强统计结论。
6. Dashboard 有一个 operator decision 写入口，其余大部分是只读；需要继续防止前端演变成交易终端。
7. 研报和 docling 相关模块正在活跃开发，数据版权、PDF 本地路径、来源可追溯和解析质量要作为独立审查点。
8. P19 基础平台闭合不等于策略生产化闭合；alpha191、mid-trend、strong-winner、tech bottleneck production admission 都需要单独验收。

## 19. 建议和专家讨论的问题

建议重点让专家看这些问题：

1. 数据层：当前 `market_daily_bar`、分钟线、财报 PIT、行业/概念历史归属是否足够支持严肃回测？
2. 因子层：`manual_v1` 和 approved-only scoring 的关系是否应重构？当前 2 个 approved factor 是否太少？
3. 回测层：LHB、Mid Trend、Tech Bottleneck 是否共享统一成本、滑点、停牌、涨跌停、T+1、成交可得性约束？
4. 策略层：EOD publish 的 official artifacts、Dashboard replay、experimental research outputs 如何做版本冻结和审计？
5. 风险层：`DEGRADED_READY` 是否应允许策略发布？哪些 partial success 必须阻断？
6. 研报/新闻层：source confidence、copyright、local PDF、docling extraction quality 如何进入证据评分？
7. 前端层：当前工作台是否满足专家复核路径？是否需要“策略证据链一页式审计”？
8. 运维层：315M 分钟线和 358M 因子长表的分区、索引、归档、备份恢复策略是否足够？
9. 人工闭环：operator decisions 样本较少，是否需要强制结构化记录复核动作，提升后续 outcome analytics 的价值？
10. 生产边界：如果未来要从 shadow 到 production watchlist，需要哪些审批、风控、回滚和审计表？

## 20. 推荐给专家看的入口文档

- `README.md`
- `docs/quant_system/04_target_architecture.md`
- `docs/quant_system/65_p19_platform_phase_index.md`
- `docs/quant_system/66_p19_release_readiness_audit.md`
- `docs/quant_system/67_p19_final_smoke_matrix.md`
- `docs/quant_system/68_p19_final_release_runbook.md`
- `docs/quant_system/69_p19_final_platform_closure_completion.md`
- `docs/daily-close-pipeline-runbook.md`
- `docs/daily-factor-pipeline-runbook.md`
- `docs/intraday-pipeline-runbook.md`
- `docs/dashboard-workbench-runbook.md`
- `docs/canonical-frontend.md`
- `docs/research/lhb_shortline_strategy_development_summary_20260609.md`
- `docs/research/mid_trend_round2_optimization_runbook.md`
- `docs/research/mid_trend_soft_ownership_runbook.md`
- `docs/watchlist-diagnostics-runbook.md`

