# 02 — Data Freshness & Consumer Contract Recovery Plan (M0.6 核心交付)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019` @ `1149c763`+.
Scope: 平台级数据新鲜度与消费契约审计 + 各停滞数据链恢复方案。
Method: 从 `strategy_daily_eod` / `strategy_eod_publish` / `run_platform_ready_build_cron` / `scripts.daily_pipeline` / crontab / launchd 实际消费代码**反向追踪**全部输入，而非按表名抽查。
Status vocabulary: repaired-verified / designed-not-executed / permission-blocked / remaining-gap.

## Verdict: PARTIAL — 事实审计完成；统一 Gate 与各链恢复方案已设计；**未做任何生产写/调度变更，等待逐项批准**

---

## 1. 系统性结论（比单条数据链更重要）

审计确认了用户判断：**平台存在多条"上游停更、下游静默降级、任务仍报 success"的数据链**，且这不是 6-7 张表的问题，而是一个结构性缺陷：

| 共性模式 | 已确认的实例 |
|---|---|
| 一次性回填/静态工件被当作每日输入消费 | TDX 竞价回填(9-07停)、MidTrend 静态目录(6-12/6-28冻结)、regime CSV(6-05停，已修)、mid_trend 顶层 funnel(5-19) |
| 下游 fail-open：缺失时回退默认值/旧文件/日线代理，仍报 success | `auction_enhanced_score` 回退日线代理、mid_trend 空切片 warn-only、watchlist 缺失回退 score 表、regime 默认 1.0(已修复) |
| `job_status=success` 仅代表"任务执行了"，不代表"数据新鲜/完整" | `check_strategy_daily_eod_dependencies` 的 `intraday` 门只查 `minute5_status`，不查 `factor.stock_intraday_features_daily` 实际日期 |

**根因（代码级）**：`strategy_daily_eod.py:1061-1103` 的依赖检查以 `ops.daily_pipeline_status` 的三个执行状态为唯一判据。`lhb_shortline` 声明 `("common","intraday")` 两个依赖键，其中 `intraday` 仅要求 `minute5_status in {success, partial_success}` —— 即只要 5 分钟线**采集任务**成功就放行，完全不验证该策略**实际消费的表**是否新鲜。

---

## 2. 全量依赖矩阵

完整矩阵见 `docs/research_upgrade/02_data_dependency_matrix.csv`（32 项，含类别/来源/最新日/调度/消费函数/缺失行为/建议状态条件）。摘要分类：

### 2.1 健康链（当日数据，已验证）

`market_daily_bar`(10-19,51.4M)、`stock_minute_bar`(10-19,raw+qfq 各 199万/日)、`trading_calendar`(至 2027-02)、`asset_status_daily`、`stock_score_daily`、`stock_technical_features_daily`、`lhb_event_features_daily`、`lhb_top_list/inst_daily`、竞价分钟/快照(观察池,10-20)、news 三件、EOD 产物目录。

### 2.2 正式每日输入但已停滞/缺失（核心问题）

| # | 输入 | 最新 | 缺口 | 消费方与当前行为 |
|---|---|---|---|---|
| 11 | `stock_auction_bar` **open_call** | **2026-09-07** (tdx源 6.91M行 2018→) | 停更 6 周 | `lhb_shortline_v1.load_frames` → `_attach_..._auction_score` entry 侧字段；缺失→**静默改用日线代理值** |
| 12 | `stock_auction_bar` **close_call** | **2026-06-09** (tushare源 1.94M行 2025→) | **停更 4 个月**，且 tushare 是唯一历史来源 | 同上 signal 侧 `signal_close_auction_return`/`entry_open_vs_signal_close` gap 字段；同样静默日线代理 |
| 17 | `factor.stock_intraday_features_daily` | **2026-08-03** (5193只×10特征/日) | 停更 10 周 | `lhb frames` 回测特征、`mid_trend_intraday_risk_overlay.py:389`、`intraday_factor_eval.py:144`；CLI `build-intraday-features-daily` 存在但**无任何调度** |
| 18 | `factor.industry_intraday_features_daily` | **2026-08-03** | 同上 | `intraday_factor_eval.py:187` 等研究消费 |
| 22 | regime CSV | ~~2026-06-05~~ | M0.5 已重建+fail-closed，**待受控发布** | `tech_bottleneck_v1` 市场敞口（必需） |
| 25 | 顶层 `mid_trend_watch_funnel_detail.csv` | **2026-05-19** | 兜底文件陈旧 5 个月 | EOD mid_trend 当日版缺失时兜底使用 |
| 26/27 | MidTrend 两静态目录 | 本地缺失(远端冻结 6-12/6-28) | `midtrend_v2_top10_candidate`/`trade_changes` 切片自 6-13 起**每日为空(warn-only)** | `strategy_daily_eod.py:1283,1303` |

### 2.3 条件依赖 / 近似闲置（按需恢复或退役）

- `market.adjustment_factor` (8-27停)：唯一消费者是 `minute_backfill.derive_qfq_minute_bars_from_raw_job`（内层 lateral join，无因子行→该日 qfq 行 0 产出→`derive rows do not match` → **job 标记失败，非静默**）。**日常 minute5 不受影响**——`daily_close_pipeline.load_latest_adjustment_factors` 直接从 `market_daily_bar` 的 qfq/raw close 推导因子，不走该表。
- `market.corporate_action` (7-27停)：仅 `data_audit.py` 注册引用，**无实际消费者** → P2 确认退役。
- `market.stock_auction_detail` (6-09,58行)、`staging.tushare_stock_auction_bar` (空)：无消费者 → P2。
- `strategy_lab_tech_bottleneck/2026-06-18`、`tech_bottleneck_evidence_workflow_20260619`：tech_bottleneck 的**二级兜底路径**，主路径（当日目录）正常 → 休眠兜底，不紧急但应在矩阵中标注版本。

### 2.4 有意冻结的静态研究输入（非新鲜度问题，需版本化声明）

- `serenity_bottleneck_baseline_...20260605` (148只冻结宇宙，发布时按日 stamp)
- `dragon_case_curated_library_failure_v2_1.csv` / `lhb_risk_feature_case_detail_v2_1.csv` / `dragon_case_lhb_alignment_audit_2024_2026.csv`（策展案例库，LHB 每日管线必需输入，有意冻结）
- `open_auction_watch_universe_latest.csv`（观察池定义，6-10 版）

---

## 3. 调度链与依赖顺序（现状）

```
[crontab] 09:15-09:25 竞价快照(观察池) / 09:40+15:10 竞价分钟(观察池)
[launchd/cron] daily_pipeline --stage daily → minute5 → deps → market_monitor
               → 产出 market_daily_bar / stock_minute_bar / lhb表 / status表
[21:00] finalize: retry_failed → market_monitor → deps → health → ops.daily_pipeline_status
[launchd 20:00] run_platform_ready_build_cron:
   public_news_refresh → free_enrichment → daily_factor(score)
   → technical_features → lhb_shortline(event_replay+watchlist, 读案例库三文件)
   → watchlist_default → finalize → strategy_daily_eod → platform_ready_check
[launchd 22:15] dashboard-daily-sync: 产物同步至 stock-prod 外网
[22:4x] strategy-eod-publish / eod_auto_repair: 发布+manifest+readiness
```

**不在任何调度中**：`build-intraday-features-daily`、`sync-tushare-auction-bars`、TDX 竞价增量、`corporate_actions` 写入、regime 每日更新、MidTrend 静态目录再生。

---

## 4. 各数据链恢复方案（按优先级）

### P0-A. 竞价日频 `stock_auction_bar` —— 推荐「Tushare 同步恢复为主，TDX 保留 open_call 补充」

**事实**（per-source×phase 实测）：

| source | phase | 区间 | 说明 |
|---|---|---|---|
| tushare | open_call | 2009→2026-06-09 | 双来源重叠多年 |
| tushare | **close_call** | 2025-01→2026-06-09 | **唯一来源**，TDX 从未提供 |
| tdx | open_call | 2018→2026-09-07 | 回填停于此 |

- **方案 A（推荐）**：恢复 `sync-tushare-auction-bars` 每日调度。它是 close_call 的**历史唯一来源**，可同时补回 open_call。需先查明 6-09 停因（配额/token/调度移除），`--ts-codes` 需全市场代码清单（从 `core.asset_master` 取）。CLI 现成：`sync-tushare-auction-bars --start-date --end-date --ts-codes`。
- **方案 B**：TDX 每日增量。只能提供 open_call，close_call 仍缺 → **不足以单独恢复**。且 TDX 是一次性本地文件导入路径，无现成每日 CLI。
- **方案 C（否决）**：用 `stock_auction_minute_bar` 聚合。实测该表仅 open_call、仅观察池 ~50-80 只（`open_auction_watch_universe_latest.csv`），且缺 `vwap`/`order_count`/`volume_unit` 字段语义 → 无法等价替代全市场日频表。**未经字段口径与重叠期等价性验证不得覆盖 TDX/tushare 历史数据**。

**影响量化**：`auction_enhanced_score` = layer_score + gap 档位分 + signal_return 档位分；close_call 缺失使 `entry_open_vs_signal_close` gap 与 `signal_close_auction_return` 全部落到日线代理（`_lhb_shortline_daily_auction_score_fallback` `combine_first` 填充），**auction 增强分退化为"日线估算版"已达 4 个月**。影响面：dashboard 回测的 `auction_enhanced_rerank` TopN 重排与 `review_scored_candidates`。**每日 watchlist→EOD review 不消费该分**（`build_lhb_shortline_strategy_eod` 只读 watchlist CSV）→ 契约分类：增强输入 → **DEGRADED（可见）而非 BLOCKED**。

### P0-B. Intraday 特征 —— 恢复调度 + 缺口回填 + 幂等

- 停因：`build-intraday-features-daily` CLI 存在但从未接入 `run_platform_ready_build_cron` / launchd（最后运行 8-03）。
- 方案：① 在 platform_ready 链 `technical_features` 之后插入该步（依赖 minute5 完成，放 lhb_shortline 之前）；② `backfill-intraday-features-daily` 回填 8-04→今日缺口；③ 幂等（`INSERT ... ON CONFLICT (trade_date,asset_id,feature_name,adjust_type)` upsert 已具备）；④ 覆盖率检查：当日行数≈市场股票数×特征数。
- 消费侧质检（`morning_return`/`close_to_vwap`/`intraday_return` 各自单列检查覆盖率，不可用整表 MAX 判定）。

### P0-C. 统一 Data Freshness Gate（见 §5）

### P1-A. `adjustment_factor` / `corporate_action` —— 降级为条件恢复

- 日线 hfq/qfq 与 minute5 的 qfq 均自 `market_daily_bar` 推导，**不受该表停滞影响**（8-27 后 qfq 分钟线仍正常产出，已实测 10-19 有 qfq 行）。
- 真正受影响场景：对 8-27 后除权股执行**历史分钟回填 derive** —— 内层 lateral join 无因子行 → 该日 qfq 行 0 → job 显式失败（**非静默**）。
- 方案：恢复 `corporate_actions` 定期写入（或改 derive 逻辑同样走 daily_bar 自推导，与 minute5 口径一致），消除双口径。**优先改口径复用 `load_latest_adjustment_factors`**，而非恢复一张近似无人消费的表。
- `corporate_action` 表无消费者 → 建议标注 deprecated 候选。

### P1-B. MidTrend 静态依赖

- 从 stock-prod 恢复 `current_mid_trend_..._20260612` 与 `midtrend_pit_..._20260628` 两个目录到本机（只读复制，远端原件不动），消除每日空切片 warn-only。
- 顶层 `mid_trend_watch_funnel_detail.csv` 兜底：当日版缺失时不应静默用 5-19 旧文件 → 改 DEGRADED 契约（fallback_used=true + degradation_reason 写入 manifest）。
- 不修改任何正式策略参数；静态目录按版本化目录名管理。

### P1-C. Manifest/Readiness 扩展（见 §5.4）

### P2. `staging.tushare_stock_auction_bar`(空)、`market.stock_auction_detail`(58行)、`market.corporate_action` —— 确认正式功能依赖性，建议退役或标注"非每日输入"，避免修复无用链。

---

## 5. 统一 Data Freshness & Consumer Contract 设计

### 5.1 原则

1. **从消费者出发**：每条输入的健康度由"消费它的策略/函数"定义，不做全表一刀切。
2. **`job_status=success` ≠ 数据健康**：执行状态与数据新鲜度分属两个维度，分开呈现。
3. **不一刀切 fail-closed**：可选增强缺失 → `DEGRADED`（可见 + 降级契约）；必需输入缺失 → `BLOCKED`（禁止正式发布）；完整 → `READY`。
4. 检查必须覆盖：最新交易日 vs **预期交易日**（`market.trading_calendar`，非"昨天"）、**覆盖率**（应有股票数/应有行数）、**中间日期断档**（不只是 MAX）、**实际被消费**（未消费的陈旧表不告警、只标注）。

### 5.2 输入分类（每条输入注册时声明）

| 类别 | 判定 | 缺失时 |
|---|---|---|
| `required_daily` | 当日必需且到覆盖阈值 | **BLOCKED**：禁止该策略正式发布 |
| `optional_enhancement` | 增强因子 | **DEGRADED**：允许发布但 manifest 显式标注 `fallback_used`+`degradation_reason`，由策略级契约决定可发布性 |
| `conditional` | 仅特定任务消费（如历史回填） | 仅当该任务运行时检查，平时标注即可 |
| `static_frozen` | 有意冻结的研究输入 | 版本校验（path+hash），不做日期新鲜度检查 |
| `deprecated/unused` | 无消费者 | 不参与 Gate，仅清单标注 |

### 5.3 检查维度（可复用，非 per-table 特判）

```
DataHealthCheck(input) →
  expected_date   = trading_calendar 最近已收盘交易日（按消费窗口取：竞价类取当日09:25前、EOD取收盘日）
  latest_date     = MAX(数据日期列)
  coverage        = 当日有效行数/应有基数(全市场|观察池|宇宙|特征数)
  gap_days        = expected_date 与 latest_date 之间的交易日数（中间断档同样计入）
  is_consumed     = 注册表中的消费方非空
  → READY | DEGRADED | BLOCKED（按 §5.2 类别映射）
```

时间口径注意：9:15 快照/9:40 分钟/收盘后三类输入的"预期日期"必须分别按各自可用窗口计算，不能用统一 MAX 比较。

### 5.4 Manifest / Readiness 新增字段（每条策略输入一条记录）

`input_name, input_date, expected_date, coverage, source_version, fallback_used, degradation_reason, health_status(READY/DEGRADED/BLOCKED), consumer`。
Readiness 由"全部 required 输入 READY 且 optional 降级在契约允许内"推导，不再等于 job_status。

### 5.5 已确认的消费者-契约映射（本审计产出）

| 策略/消费 | required_daily | optional_enhancement | 当前缺失实际影响 |
|---|---|---|---|
| tech_bottleneck EOD | daily_bar, 种子宇宙, **regime(待发布)** | — | regime 缺失已 fail-closed |
| lhb watchlist→review | daily_bar, lhb事件特征, score表, 案例库三文件 | **auction_bar**, **intraday特征**, watchlist.csv(缺→score兜底) | 回测增强分/盘中特征降级为代理，非阻断 |
| mid_trend EOD | daily_bar, score表 | funnel兜底, 两静态目录 | 切片空/旧兜底→DEGRADED |
| 回测/dashboard | 同各策略 | auction, intraday | rerank 精度下降 |

---

## 6. 执行边界（待批准清单）

| 事项 | 状态 | 需批准 |
|---|---|---|
| 事实审计+矩阵+方案（本文件） | 完成 | 审核 |
| Regime+fail-closed 受控发布 | 已验证待发布 | 已在 Preflight 单列批准 |
| Tushare 竞价同步每日调度启用 + 历史回填 6-10→今 | 设计完，CLI 现成 | 生产调度+配额/token 确认 |
| intraday 特征接入 platform_ready + 8-04 起回填 | 设计完，CLI 现成 | 生产调度+批量回填 |
| derive_qfq 口径改走 daily_bar 自推导 | 设计 | 代码变更批准 |
| MidTrend 两目录恢复 + 兜底契约 | 待执行(只读复制) | 文件恢复确认 |
| Gate 实现（manifest/readiness 字段+检查器） | **核心检查器已实现**：`src/stock_research/data_freshness_gate.py`，11 项行为测试绿；已按 §5.2 分类对 13 条输入实测（7 READY / 4 DEGRADED / 1 NOT_EVALUATED / 0 BLOCKED），证据 `outputs/research/data_freshness_health_20261020.csv`；manifest/readiness 集成仍待批准 | 集成任务批准 |
| P2 表退役确认 | 待确认 | 确认即标注 |

**本阶段未做**：任何生产库写入、cron/launchd 启用、配置变更、策略行为变更、部署。所有恢复动作均为设计/隔离测试状态。

## 7. 证据路径

- 依赖矩阵：`docs/research_upgrade/02_data_dependency_matrix.csv`
- Gate 模块与测试：`src/stock_research/data_freshness_gate.py`、`tests/test_data_freshness_gate.py`（11 passed）
- 实测健康报告：`outputs/research/data_freshness_health_20261020.csv`（as_of 2026-10-19 post_close；EM 竞价分钟按 intraday 窗口评估，体现"不同消费窗口不同预期日"原则）
- 竞价分源：`SELECT source,auction_phase,max(trade_date) FROM market.stock_auction_bar GROUP BY 1,2`
- 依赖门缺陷代码：`src/stock_research/strategy_daily_eod.py:1061-1103`
- 竞价降级代码：`src/stock_research/lhb_shortline_v1.py:1549-1647`（`_lhb_shortline_daily_auction_score_fallback`）
- 复权链：`src/stock_research/minute_backfill.py:380-470`（derive+lateral join）、`daily_close_pipeline.py:854-`（daily_bar 自推导）
- regime 修复：`docs/research_upgrade/02_regime_release_preflight.md`
