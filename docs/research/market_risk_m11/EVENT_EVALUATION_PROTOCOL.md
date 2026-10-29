# 事件评价协议（M1.1修正版）
- 评价窗口外的事件标 `NOT_EVALUATED`，不记 MISSED_EVENT（修正M1把2019-25历史事件误记为漏报的边界错误）。
- 双覆盖率分开：Onset Active（onset当日仍在WATCH+）与 Prior Warning（前5/10/20/40交易日曾出现）。
- 连续 WATCH+ 区间=一个 episode（ALERT_EPISODE_LEDGER.csv）；同一周期内多日预警不重复计成功。
- 提前解除单独记录 released_before_onset。
