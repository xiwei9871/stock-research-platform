# 状态机审计 — R2.1.1

对照 `PRE_REGISTERED_RULES.json` 逐条核对 `analyze_r21.py` 原实现，发现 **4 处不符**（已修复并经合成序列单元测试验证）：

| # | 规则 | 原实现 | 影响 |
|---|---|---|---|
| 1 | HIGH_PRESSURE 需 10 日 | `upd()` 统一 5 日 | HIGH 进入过早——状态被高估 |
| 2 | AS≥65→RECOVERING 需 10 日 | 5 日 | 恢复进入过早 |
| 3 | RECOVERING→NORMAL "WP<60 held 10d" | 实现为 20 日 | 状态滞留偏长 |
| 4 | 单一共享 `hold` 计数器 | 同日多条 `upd()` 共用，且条件跨分支不隔离 | 计数交叉污染，可能异常跳转 |

**修正后影响：868 个交易日状态标签发生变化**（约 52% 样本），HIGH_PRESSURE 日数显著减少，部分原 HIGH 降级为 ELEVATED/WATCH。状态转移 24→新转移数见 WARNING_TRANSITIONS.csv。

单元测试 `test_r211.py`：合成 WP/AS 序列验证每条转移边界的 hold 天数精确性、计数器在 4 日间隙后重置、跨条件计数隔离。全部通过。

其余规则核对一致：WATCH 进入 5d、ELEVATED 进入 5d、HIGH 备选条件（WP≥75 且 outshare40≥0.6, 10d）、RECOVERING 进入（WP<60, 5d；last_hi 40d 内）、RECOVERING→WATCH 再进入 5d。
