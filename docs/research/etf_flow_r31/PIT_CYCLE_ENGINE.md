# PIT 资金周期引擎（R3.1）
单向逐日；每日只读 i<=t。

- **检测**：Σ20d 净流<0 且 outshare20>=0.55 连续 10 日 → `detected`=当日。
- **参考锚点**：`economic_start`=detected 前 120 日内累计余额 B 的最高点（只用过去）；`B_start=B[es]`、`AUM_start=aum[es-1]`，检测后立即冻结，不回写。
- **每日 PIT 特征**：`pdepth=max(0,B_start−B_t)/AUM_start`；`ddur`=自 detected 交易日数；`eelap`=自 economic_start 日数（经济起点为事后标签，单独保留）；`vel5/vel20`=近5/20日净流 ÷ 当期 AUM ÷ 天数（%/日，单位统一）；`accel=vel5−vel20_prev20`；`pstate` 五态由当日 vel/F20/accel 决定。
- **关闭**：`B_t>=B_start` → CLOSED；数据末端仍开 → OPEN。
- **事前/事后分离**：detected 之前的日子 `pcyc=""`（R3 曾回填至 econ_start，已修正）；`economic_start` 仅作事后分析字段。
- **截断重放**：`engine(df[:T])` 在 T−1 及之前每日的 pcyc/pstate/pdepth/ddur 与全量运行逐日相等（400/900/1400 三截点×9 组全 PASS）。
