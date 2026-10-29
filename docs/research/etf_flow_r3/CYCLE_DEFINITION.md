# 资金周期定义（评估前冻结，flow-only，PIT）

## 原则
- 只用历史资金数据（公司行为修正后 `flow_use`），不用任何价格/未来信息决定周期起止。
- 单向前行在线算法；事后统计字段与事前状态字段分开（`live_*` vs `post_*`）。

## 算法 A（主口径）：资金余额回撤法
- `B_t = Σ flow`（自 2020 起逐组累计净申购金额，亿元）。
- **开启确认**：日 T 满足 `Σ20d flow < 0` 且 `outshare20 ≥ 0.55` 连续 10 个交易日 → 周期开启；`cycle_start = argmax(B_t) over [T−120, T]`（只用过去，可在线）。
- **关闭**：`B_t ≥ B_cycle_start`（累计余额回到周期起点水平）当日为 `live_end`。
- **周期内状态**（每日，事前可算）：
  - `WITHDRAWING`：`vel20 < 0`（20日净赎回速度为负）
  - `WITHDRAWAL_DECELERATING`：`vel20 < 0` 且 `accel > 0`（仍在撤离但减速）
  - `FLOW_STABILIZING`：`|vel20| < 0.05%/d`
  - `REACCUMULATING`：`vel20 > 0` 且 `F20 > 0`
- 不结束规则：单/几日净申购不结束周期；只有余额回到起点才关闭。
- `right_censored`：数据末端仍开启 → `OPEN`。

## 算法 B（对照）：滚动确认连续区间
- 撤离期 = `F20 < 0` 且 `outshare20 ≥ 0.5` 的连续日段（≥10 日），不拼接。
- 与 A 在 `CYCLE_DETECTION_AUDIT.md` 对照：周期数、起止、2026 解释差异。

## 维度（事前可算）
- `depth(t) = max(0, B_start − B_t) / AUM_cycle_start`（累计撤离比例）
- `duration(t)`：cycle 开启后交易日数
- `vel5/vel20`：近5/20日净申购/AUM_cycle_start（比例/日）
- `accel = vel5 − mean(vel, prior20d)`
- `breadth`：流出日 `out_aum/tot_aum`（含 `SMALL_UNIVERSE` 标记，n<8 组）

## 深度分箱（研究分箱，非风险等级）
0–10 / 10–20 / 20–35 / 35–50 / >50 %（周期内峰值 depth）。
