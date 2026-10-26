# P1d.3 — 消费者切换矩阵（逐消费者灰度）

切换单位 = 单个消费方的 `qualification_mode`；每步独立回归 + 与 corrected_shadow 对照 + 可立即回退。

| 消费方 | 当前模式 | 切换目标 | 切换方式 | 预检查 | 回滚 | 风险 |
|---|---|---|---|---|---|---|
| `vectorized_topn_backtest` | legacy | corrected_shadow → verified_v2 | 调用点参数 | 灰度门禁 4 窗口已证 v2≡cs | 参数改回 | 中——已测 0/15bps 端到端 |
| `backtest.load_backtest_inputs/_bars`（retention 等） | legacy join | corrected 读路（加 qualification_mode 参数，同 TopN 模式） | loader 参数 + `use_status_flags` | bar flag 与 corrected 一致 | 参数改回 | 中 |
| `dashboard/backtests` | legacy join | 同上 | loader 参数 | 同上 | 同上 | 低 |
| `intraday_risk_control_v2` / `intraday_risk_filter_backtest` | legacy join | 同上 | loader 参数 | 同上 | 同上 | 低 |
| `mid_trend_shadow_backtest` | legacy join | 同上 | loader 参数 | 同上 | 同上 | 低 |
| `serenity_tight3b_c2_experiment` | legacy join | 同上 | loader 参数 | 同上 | 同上 | 低 |
| `dragon_case_library` | 已走规则引擎（P1d.2 修复） | 无需迁移 | — | — | — | 已切 |
| `lhb_eligibility` | 已走规则引擎 | 无需迁移 | — | — | — | 已切 |
| `market_emotion_state_v1` | 存量 v1 涨停计数 | **NEEDS_REVALIDATION**——重算依赖输入后再定 | 独立任务 | — | — | 高，暂不切换 |

## Gate（每消费者独立）

1. `verified_v2` 读出 flag == 同窗口 corrected_shadow（已证 0 mismatch）；
2. `rule_unknown/data_insufficient` 行 fail-closed；
3. 该消费者回归套件 0 新失败；
4. 与 legacy 基线的差异全部可归因 rule_id/缺失态。
