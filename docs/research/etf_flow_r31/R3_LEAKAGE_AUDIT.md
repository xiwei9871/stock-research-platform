# R3 前瞻偏差审计（确认 3 处 + 附注）

基线 `cc9a376d`。对 `analyze_r3.py` / `analyze_r3b.py` 逐行复核：

## 确认泄漏

**L1 事后深度分箱**：`DEPTH_DURATION_RISK_RESULTS.csv` 用 `depth_max`（全周期最大撤离，周期结束才知）对 `open_confirm` 日的前向收益分箱。35–50% 箱的事件在观察当日真实深度可能只有 15%——**分组使用了未来信息**。R3 "35–50% 箱最浅"的结论建立在此泄漏上，不可信。

**L2 事后持续时间**：`dur_days` 为周期全程时长，H2 "dur≥90d 风险更浅"的 dur≥90 分组在观察日不可知（当日仅能知 elapsed）。

**L3 周期归属回填**：`flow_cycles_A` 确认后将 `fcycle/fstate` 回填至 `[economic_start, end]`——`economic_start` 到 `detection` 之间的日子在 `FUND_FLOW_CYCLE_DAILY.csv` 中被标为在周期内，而当日观察者尚不知周期存在。depth 序列同样回填。

## 检查后排除

- 周期确认日 `i_open` 本身是 PIT 合法（Σ20d+outshare20 均为历史滚动量）；前向指标从 i_open 起算无泄漏。
- cycle_start 的 lookback argmax 只用过去数据，PIT 合法。
- ETF 分组为 PIT 上市日纳入，无未来成员信息。
- 右端 fwd 全 NaN，未计无风险 ✓。
- 多组同市场事件确实重复暴露（43 周期跨 9 组共享 6 个市场周期）——R3 已标注，R3.1 按周期聚类。

## 未改

资金数据、公司行为修正、分组、F 窗口、周期确认规则全部冻结。
