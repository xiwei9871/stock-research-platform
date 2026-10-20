# 03 — Auction Source Validation (M0.7 / P0-4)

Date: 2026-10-20. Status: **probe completed — primary source BLOCKED by API
permission; recovery needs user-level action or new collector**.

## 实测探测结果（只读，无库写入）

| 来源 | 探测 | 结果 |
|---|---|---|
| **Tushare** `stk_auction_o`/`stk_auction_c` | token 存在于 `config/local_secrets.json`；对 2026-06-05 两相做只读查询 | **API 无权限**：`抱歉，您没有接口(stk_auction_o)访问权限` — 订阅/权限已失效或从未含该接口 |
| **TDX** | `staging.tdx_stock_auction_bar.source_endpoint='tdx:0x0fc6'`，payload 为二进制记录解析字段（`record_hex/price_milli/time_minutes/order_count`） | **仓库内无 TDX 采集代码**；6.91M 行由外部工具导入（一次性回填 6-10→9-07）。日内增量需该工具或新集成 |
| **Eastmoney minute** | `market.stock_auction_minute_bar` | 仅 `open_call`、仅观察池 ~50-80 只、无 `vwap/order_count/volume_unit` → **不可等价替代**全市场日频表 |

## 历史来源分布（stock_auction_bar 实测）

| source | phase | 区间 | 结论 |
|---|---|---|---|
| tushare | open_call | 2009→2026-06-09 | 双源之一，6-09 停 |
| tushare | **close_call** | 2025-01→2026-06-09 | **唯一来源**，停更 4 个月 |
| tdx | open_call | 2018→2026-09-07 | 一次性回填，**从未提供 close_call** |

## 影响（与消费契约）

`auction_enhanced_score` 的 signal 侧（close_call）自 6-10 起、entry 侧
（open_call）自 9-08 起全部落到日线代理 —— 仅影响回测 `auction_enhanced_rerank`
TopN 与 `review_scored_candidates`，每日 watchlist 不消费 → **DEGRADED 可见，
非 BLOCKED**。

## 恢复路径评估

| 方案 | 可行性 | 缺口 |
|---|---|---|
| A. Tushare 每日同步恢复 | **需用户续订/授权 `stk_auction_o/c`** — 账号级动作 | 若开通可双相恢复，是最接近原状的方案 |
| B. TDX 日内增量 | 需原外部采集工具或新 TDX 集成 | 只能补 open_call；close_call 仍无解 |
| C. EM 分钟聚合 | 仅 open_call+观察池 | 不可作为正式替代；可作观察池补充 |
| D. 新 close_call 采集器 | 在 14:57-15:00 对全市场做收盘竞价采集（EM 分钟/快照口径扩相） | 代码变更，需单独设计评审 |

## 量化影响（实测，2026-10-20 补做）

对真实 dashboard 回测 trades（288 笔，145 个交易日，2026-01-05→10-15）做双轨评分：
`_attach_lhb_shortline_v1_auction_score` 分别喂真实 `stock_auction_bar` 行与空表（→日线代理）：

| 指标 | 结果 |
|---|---|
| 分数有差异的交易 | **21/288（7.3%）** |
| 差异幅度 | 全部在 ±10~20 分档（0 笔 ≥25） |
| mean \|Δ\| | 0.73 分 |
| **Top5 成员翻转** | **0/145 日** — 增强分未改变任何一天的 Top5 归属 |
| 9-07 之后（26 笔） | Δ=0（两轨都无数据，无法反事实） |

解读：竞价增强的真实贡献存在但有限——layer_score（±100~80 档）主导排序，竞价分只
在 8% 交易上施加 ±10-20 微调，未翻转 Top5。**"填零错误加分"不成立**：缺失时
`signal_return=0`（中性），但 gap 字段语义确实被替换（日开/昨收缺口≠竞价缺口），
语义漂移 > 分数漂移。证据：`outputs/research/m0_7_lhb_auction_impact_20261020.csv`。

**成本/价值评估**：竞价增强对 TopN 影响可忽略（0 翻转），价值集中在 gap 语义真实性；
Tushare 续订的边际研究价值有限 → 支持"暂不购买权限"决定。close_call 语义缺口更大
（4 个月）且唯一来源是 Tushare；若其价值不足，可将 close_call 特征在契约中正式
标记 `deprecated`，消除"假装存在"的假象。

## 修订方案（用户 2026-10-20 决定）：TDX 开盘 + 5min 收盘代理，不买 Tushare

### 5 分钟行情核验（实测结论，全部通过）

在 `market.stock_minute_bar`（freq=5min, adjust_type=raw）上：

| 检查项 | 结果 |
|---|---|
| 最后一根 K 线标签 | 恒为 `15:00`；每日 48 根均匀网格（首根 09:35）→ 窗口为 **14:55–15:00**，含约 2 分钟连续竞价 + 3 分钟收盘集合竞价 |
| 15:00 close == 日线 raw close | **5,186/5,186 完全一致**（2026-10-19）；连续 5 个交易日全对 |
| 历史对拍（2026-06-08） | close_call.close == 15:00 close：5,198/5,198；close_call 量 ≈ 全日 **19.1%** |
| 缺失/停牌/零成交 | 5 日测试 0 缺失、0 零量（当日 trade_status 全 '1'）；**但发现 14:55 close=0 脏数据存在**（需 NULLIF 保护） |
| 15:00 bar open 位置 | 在 **14:55**（窗口起点），非 14:57；open==close 仅 20.8% → bar 内确有连续竞价成分 |

结论：**收盘价信号可直接复用**（5min close = 日线 close = 历史 close_call close）；
**尾盘涨跌幅只能作为 `last_5m_return` 新因子**（混合窗口，不得冒充 close_call_return）；
**14:57–15:00 竞价量/订单结构不可还原**（bar 内不可分）。

### A/B 对拍（真实 trades，2026-10-20 执行）

285 笔 filled trades；可验证子集 155 笔（信号日 ≤2026-06-08，真实 close_call 存在）：

| 指标 | 结果 |
|---|---|
| corr（真实 close_call_return, last_5m_return) | **0.21** —— 确为不同因子，量纲更小（真实均值 +0.55% vs 代理 +0.09%） |
| 打分项触发差异 | 20/155 笔（±10 分档） |
| **Top5 成员翻转** | **0/79 日** |
| 选中集收益 | 原/代理完全一致（avg 0.0200, med 0.0017, win 51.6%） |

`entry_open_vs_signal_close`（gap 项）在适配版**无损**：close_call.close == 日线 raw close，
只需 entry 日 open_call + signal 日日线收盘 —— TDX 恢复后该因子可活到最新日。
真正损失的只有 `signal_close_auction_return` 的严格语义 → 以 `signal_last_5m_return`
显式标记替代；竞价专有指标（竞价量/额/订单数）保持 unknown，不补零。

证据：`outputs/research/m0_8_auction_proxy_ab_20261020.csv` + `_summary_20261020.csv`。

### TDX 采集工具定位（已查明）

整套实现存在于 git 历史 `8dd57c88`（`wip/minute5-resumable-snapshot-20260917`）：

- `src/stock_research/tdx_auction_backfill.py`：`backfill_tdx_auction_date(date)` 单日全市场
  抓取（`eltdx` 客户端 `trades.opening_match_history`，0x0fc6 历史成交明细聚合）；
  `upsert_tdx_auction_rows` 幂等写 `staging.tdx_stock_auction_bar` + `market.stock_auction_bar`
  （ON CONFLICT，天然支持断点续采/重跑）。
- `tdx_auction_watchdog.py`：多日分区 + ledger 断点续采 + 月度报告。
- `scripts/run_tdx_auction_backfill_watchdog_host.sh`、launchd plist、6 个测试文件。

**停在 9-07 的原因**：任务是按 `START_DATE=2026-06-10 / END_DATE=2026-09-07` 的有界回填
设计，写完 completion sentinel 后 launchd 退出——从未配置"每日增量"模式，非工具失效。

`eltdx==3.1.3` 已装在 venv 但未入 pyproject → 需补依赖声明。

### Freshness Gate 注册表更新（已实施）

- `open_call` 拆为 `open_call:tdx`（前向来源，OPTIONAL_ENHANCEMENT → 当前 DEGRADED）
  与 `open_call:tushare`（STATIC_FROZEN → READY）；
- `close_call` 改 STATIC_FROZEN（无前向来源，仅历史可复现）；
- 新增 `stock_minute_bar(5min:raw)`（OPTIONAL_ENHANCEMENT，consumer=`auction_proxy:last_5m`）。
- 修复：表级 STATIC_FROZEN 曾被误判 BLOCKED（file_exists 未注入）。

Sweep 2026-10-19：19 项 = **14 READY / 4 DEGRADED / 1 NOT_EVALUATED**。

### 真实 TDX 只读抓取验证（2026-10-20 执行，dry_run，零写库）

使用生产原语（`load_tdx_auction_universe` → `fetch_tdx_opening_matches` →
`build_tdx_market_row`，捕获行但不 upsert）：

| 日期 | universe | matched | missing | failed | unsupported | 耗时 |
|---|---|---|---|---|---|---|
| 2026-09-07（已有） | 5,181 | 5,145 (99.3%) | 34 | 0 | 2 | 122s |
| **2026-09-08（缺口首日）** | 5,181 | **5,141 (99.2%)** | 38 | 0 | 2 | 131s |
| 2026-10-19 | 5,177 | 5,136 (99.2%) | 41 | 0 | 0 | 136s |

- **价格一致性 100%**：matched 行的 09:25 撮合价与 `market_daily_bar` raw open
  逐只全等（5,145/5,145、5,141/5,141、5,136/5,136）。
- 与已有 DB 行对拍（9-07）：**5,145/5,145 与库内值一致，0 mismatch**（库内 5,147 行，
  新抓少了 2 行——现为 no-match，历史抓取可能曾有其值或退市）。
- missing ~34-41/日：无开盘撮合的标的（停牌/无竞价成交），属正常空值，
  代码语义即 no-match 非 failure。
- **结论：9-08 以来的缺口数据 TDX 服务器真实可提供**，回填是执行+质控问题。

证据：`outputs/research/m0_8_tdx_readonly_probe_20261020.json`

**缺口清单（open_call:tdx）：2026-09-08 → 2026-10-20 共 25 个交易日**
（含 10-20；EM 分钟数据不构成等价替代）。

### host 脚本每日增量最小修改点

| 现状 | 问题 | 最小修改 |
|---|---|---|
| `START_DATE/END_DATE` env 固定（2018→2024 / 回填期 6-10→9-07） | 每日模式需动态日期 | env 缺省时由脚本查 `trading_calendar`：START=END=最近开放日（≤今日-1 或收盘后含今日） |
| completion sentinel | `COMPLETION_KEY` 已含日期→自然按日轮换；单日窗口完成后当日重跑自动 skip ✓ | 无需改 |
| launchd `StartInterval=60` | 回填期每分钟重试合理；日常模式浪费+日志噪声 | 改 `StartCalendarInterval`（如 17:10 每日一次，在 platform_ready 前完成）；或保留 60s 靠 sentinel 幂等（次选） |
| `MAX_JOBS=4` | 单日只有 1 个 partition | 无需改，自动收敛 |

### 生产试补申请（2 个交易日）

**范围**：`2026-09-08`（缺口首日）+ `2026-10-19`（最近日，覆盖不同时段市场状态）。
对 `market.stock_auction_bar` / `staging.tdx_stock_auction_bar` 写入
`source='tdx' AND auction_phase='open_call'` 行（ON CONFLICT 幂等）。

| 项 | 方案 |
|---|---|
| 备份 | 缺口日无既有 tdx 行 → 覆盖风险为零；仍先做行数+hash 快照留档 |
| 执行 | `tdx-auction-backfill-watchdog --start-date D --end-date D`（单日窗口）；或直接 `backfill_tdx_auction_date(D)` |
| 验收 | matched/universe ≥ 99%；价格 vs daily raw open 一致性 ≥ 99.9%；failed=0（或有文档化原因）；Freshness Gate `open_call:tdx` 对当日转 READY |
| 回滚 | `DELETE FROM market.stock_auction_bar WHERE source='tdx' AND auction_phase='open_call' AND trade_date IN ('2026-09-08','2026-10-19')` + staging 同条件；PK 含 source 不触及其他来源 |
| 预计耗时 | ≈2-3 分钟/日（实测 122-136s） |

批准后路径：试补通过 → 分批历史回填（9-08→10-20 余 23 日）→ 每日增量调度（plist 修改 + bootstrap）。

### #7a 生产试补执行结果（2026-10-20，**PASS**）

写入前检查：两表 schema 已完全兼容（`volume_unit`/`order_count`/`source IN ('tushare','tdx')`
齐备，无迁移需求）；目标日期两表 0 条既有 TDX 记录（快照已导出，空）；部署仅调用
`tdx-auction-backfill-watchdog` 单日期窗口（不动 Regime/Intraday 代码路径）。

| 日期 | universe | matched→written | missing | failed | 价格一致率 | 耗时 |
|---|---|---|---|---|---|---|
| 2026-09-08 | 5,181 | **5,141（≥99% ✓）** | 38 | 0 | **100%**（5,141/5,141） | ~2min |
| 2026-10-19 | 5,177 | **5,136（≥99% ✓）** | 41 | 0 | **100%**（5,136/5,136） | ~2min |

验收明细（全部通过）：
- market + staging 两表行数一致、distinct ts_code 一致、全 `source='tdx'`/`volume_unit='hand'`、
  payload_hash 完整；PK 重复 0；无非目标日期写入（tdx 新行合计恰为 10,277 = 5,141+5,136）。
- Tushare 历史行与其他日期 TDX 行未触碰。
- 账本：`ingest.backfill_task` 两 run 各 1 task `success`、attempts=1。
- 回滚谓词验证（未执行删除）：market `trade_date+auction_phase+source='tdx'` 与
  staging `trade_date+auction_phase+source_endpoint='tdx:0x0fc6'` 各精确命中
  5,141/5,141、5,136/5,136 —— 只覆盖本次写入行。
- 两日全行快照已导出：`outputs/research/m0_8_tdx_trial_20261020/post_*.csv`（可恢复副本）。
- Gate 单日识别：两日 `open_call:tdx` coverage = 5,141/5,136。
- 整体 Gate 仍 DEGRADED（剩余 23 日缺失）——按约定不计为试补失败。

**缺口更新：25 日中已恢复 2 日（9-08、10-19）；剩余 23 日待 #7b。**

### #7b 分批回填实施方案（待批准）

- 方式：同一 watchdog 单日窗口逐日执行（每 run 独立 run_id + 账本记录，天然断点续采）。
- 批次建议：9 月缺口（9-09→9-30，约 15 个交易日）一批验收；10 月缺口（10-09→10-20，
  约 8 个交易日）一批验收。每批后跑价格一致性+Gate 对账。
- 预计耗时 ≈2min/日 → 每批 <1 小时。
- 回滚：按日期+source/source_endpoint 精确 DELETE，与试补同构。
- **每日增量启用是独立步骤**：host 脚本动态日期 + launchd `StartCalendarInterval`
  修改、首次 cron 跑通验证，全部需单独批准（#7）。

### 最小改造方案（待正式集成审批）

1. **TDX 日更恢复**：从 `8dd57c88` 恢复 tdx_auction_backfill/watchdog/host 脚本 + 测试；
   `eltdx` 加入 pyproject；以每日 `backfill_tdx_auction_date(expected_open_day)` 接入
   platform_ready 链（不复用全区间 watchdog）；字段语义对拍已做（volume=手 vs tushare=股，
   `volume_unit` 列已区分）。**待批准：生产调度启用**。
2. **适配版增强因子（研究版，不动正式策略）**：新增
   `build_lhb_auction_observation_detail_v2`，open 侧读 open_call（任意 source，TDX 优先），
   收盘侧以 15:00/14:55 5min bar 计算 `signal_last_5m_return`，列名显式区分；
   不可还原字段（auction volume/amount/order_count/vwap）置 NULL + coverage 标记，
   不补零。**严格 PIT**：代理仅用收盘后才可得的数据（14:55/15:00 bar 于当日 EOD 可得）。
3. **对拍报告**：v1（真实 close_call 期）vs v2 的评分/Top5/收益差异已在上方给出；
   v2 对 >6-09 日期提供 gap 因子延长覆盖（至 9-07；TDX 恢复后至最新日）。
4. **Gate**：已按上表更新；`close_call` 保留"历史专有数据不可完整还原"研究限制说明。

### 结论与待办

- **当前没有可直接启用的竞价日频来源**：Tushare 权限缺失（用户级解决），
  TDX 无日内工具，EM 覆盖不足。
- 回填 `close_call` 6-10→今的历史缺口：唯一可行源是恢复 Tushare 权限后回填；
  或在 EM 上扩 close_call 采集后做重叠期等价性验证。
- **严禁**未经字段口径/时间窗/成交量额口径/撮合规则等价性验证，用 EM 派生值
  覆盖 TDX/Tushare 历史行。
- 待用户决定：是否续订 Tushare 竞价接口 / 是否立项扩 close_call EM 采集 /
  是否联系 TDX 采集工具来源方。
