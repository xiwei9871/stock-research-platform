# R3 研究协议 — ETF 资金配置周期与中期风险

主线从"预警阈值"转向"资金周期四维"：Depth / Duration / Velocity / Breadth。

## 管线
1. `analyze_r3.py`：flow-only 余额回撤法识别资金周期（定义先冻结，见 CYCLE_DEFINITION.md），逐日状态与深度 → FUND_FLOW_CYCLES + FUND_FLOW_CYCLE_DAILY。
2. `analyze_r3b.py`：深度分箱×前瞻风险、时长、加速度、广度、轮动、双时钟、失败案例、2026月度台账、OOS。
3. `plot_r3.py`：9 张图。`build_html_r3.py`：离线交互页。
4. `test_r3.py`：断言。

## 口径
- depth = max(0, B_start−B_t)/AUM_cycle_start；>100% 不截断，标 `DEPTH_GT_100` 并给当前AUM口径敏感性。
- 周期状态全部为事前可观察；起止日期为事后字段。
- 前瞻窗 20/40/60/120 交易日；右端不足排除。

## 分段
2020–23 探索 / 2024–25 验证 / 2026 touched（假设受 2026 启发，非盲测）。

## 独立单位
以资金周期为单位；周期内多日不作独立样本（深度分箱统计按周期计）。
