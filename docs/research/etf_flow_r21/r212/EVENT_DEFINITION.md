# 事件与周期定义（R2.1.2，评估前固定）

## Level A：阈值穿越
`dd_t = px_t / max(px[t-119..t]) − 1`（滚动120交易日峰值）。
首次 `dd_t ≤ −10%` / `≤ −15%` 且此前20日均在状态外 → 阈值穿越事件。

## Level B：独立风险周期
- **开启**：任一 −10% 首次穿越日（reference_peak = 当日滚动峰值）。
- **结束**（满足其一即关闭）：
  a. `dd_t > −5%` 连续 10 个交易日（回撤基本解除）；
  b. 价格创新高 ≥ reference_peak。
- 周期内记录 first_dd15（若发生）、trough、max dd、recovery_date。
- 同周期的多次 −10%/−15% 穿越只计一次。
- **敏感性**：S1 基准(−5%/10d)；S2 严格恢复(−3%/20d)；S3 仅新高。
  划分先于覆盖统计固定，不按覆盖结果调整。
- `right_censored`：数据末端仍在回撤状态 → ONGOING，不计已完成评价。

## 预警周期（episode）
WATCH/ELEVATED/HIGH_PRESSURE 的**连续区间**，退出预警集合当日结束，重新进入生成新 ID。不用固定 gap 拼接。

## 覆盖口径（三分离）
- **Active**：onset 当日仍在预警 → 主口径；另报前 5/20/60 日内是否有预警日。
- **Lead**：onset 所在/最近预警期的首次 WATCH/ELEVATED/HIGH 距 onset 交易日数（可 >60d，单列）。
- **Recent**：前 20/40/60 日是否出现预警日，区分「持续至 onset」vs「已解除」。

## 误报
- 严格：预警期开始后 60 日内无**新周期**的 −10% 首次穿越。
- 宽松：120 日同口径。
- 另列：`in_drawdown`（预警起于已深回撤中）、`risk_after_release`、`up_move`（期内指数涨>10%）、`CENSORED`（观察窗不足）。
