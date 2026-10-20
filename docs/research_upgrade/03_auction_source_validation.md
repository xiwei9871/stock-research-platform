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

## 结论与待办

- **当前没有可直接启用的竞价日频来源**：Tushare 权限缺失（用户级解决），
  TDX 无日内工具，EM 覆盖不足。
- 回填 `close_call` 6-10→今的历史缺口：唯一可行源是恢复 Tushare 权限后回填；
  或在 EM 上扩 close_call 采集后做重叠期等价性验证。
- **严禁**未经字段口径/时间窗/成交量额口径/撮合规则等价性验证，用 EM 派生值
  覆盖 TDX/Tushare 历史行。
- 待用户决定：是否续订 Tushare 竞价接口 / 是否立项扩 close_call EM 采集 /
  是否联系 TDX 采集工具来源方。
