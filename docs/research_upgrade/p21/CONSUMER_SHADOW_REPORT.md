# P2.1-C 同日公告前视 Shadow（隔离测试，未覆盖任何生产输出）

复现：`scripts/p21_consumer_shadow.py` → `consumer_shadow_summary.json` + `consumer_shadow_diff.csv`（286,704 行明细）。

## 方法

- Legacy：`announcement_date <= trade_date`（现全部消费者口径）；
- Corrected：`announcement_date < trade_date`（D+1 保守）；
- 评估网格：5,213 资产 × 1,386 个评估日（2020 起全部月末交易日 + 所有本身是公告日的交易日——泄漏面本身）。

## 结果

| 指标 | 值 |
|---|---|
| 选择发生变化的 资产×日期 | **286,704** |
| 其中报告期发生切换（period_shift） | **283,392**（98.8%） |
| income / balance / cash_flow | 95,620 / 95,565 / 95,519 |
| 受影响交易日 | **1,381** 个 |

受影响日期高度集中在**披露截止日**：2025-04-29(4,263)、2023-04-28(3,917)、2022-10-28(3,911)、2024-04-30(3,855)、2026-04-29(3,629)、2024-10-31/30、2025-10-31/30 …——每年 4 月底（年报+一季报）与 10 月底（三季报）截止窗。

## 解读

- 每个披露截止日，legacy 当天即"看到"压线公告（盘后挂网）的一批新期报表；corrected 要等下一交易日 → 选中的 report_period 回退一期。98.8% 为 period_shift 说明影响的不是"同一期选哪版"而是**整期可见性**。
- 消费路径对应：point_in_time_finance.get_latest_*、finance_ttm（TTM 期末构成期会晚一期）、fundamental_pipeline、midtrend 特征——**四条路径共用同一约定，全部命中**。
- 因子值差异与持仓/收益/换手/回撤差异：需按 corrected 口径重跑因子与回测才能量化——**属修复阶段范围**（本轮禁改正式因子/回测）。受影响日期清单（consumer_shadow_diff.csv）即回测重验收的日期全集。
- 必须重验收的旧回测：**凡使用财务因子的策略在每年 4/27–30、8/29–31、10/29–31、3/31 附近窗口的决策均可能不同**，建议全部进入 NEEDS_REVALIDATION 直至重验。
