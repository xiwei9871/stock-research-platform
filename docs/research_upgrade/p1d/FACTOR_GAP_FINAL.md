# FACTOR_GAP_FINAL — 终态因子缺口核销（P1c 收口）

口径：R2 下游重建 `minute` 阶段最终 pass（`r2_downstream_minute2.log` 末段），终态缺口与 `factor_gap_155_reconciliation.json.minute_residual_gap_*` 完全一致。

## 数字闭环

| 集合 | 数量 |
|---|---:|
| Minute eligible（= R2 修复报告 COMPLETE 集） | 2,308 资产 |
| Minute done keys / 资产 | 3,077 / 2,293 |
| **baostock key 终态 FACTOR_GAP** | **74 keys / 74 资产** |
| 其中：akshare/eastmoney 备用源已覆盖（资产有 done key） | 59 |
| 其中：**无任何 done key（真·分钟不可用）** | **15** |

## 74 资产 baostock 终态缺口清单

见 `factor_gap_155_reconciliation.json.minute_residual_gap_assets`（74 项）与
`p1c_asset_key_matrix.csv.minute_baostock_factor_gap_terminal=true` 列。

构成：科创板 688xxx 25 只 + 沪市 600/601/603/605 47 只 + 深市 002155/301117 2 只。
机理：`derived qfq minute rows do not match raw rows` —— 原始分钟线存在，但对应交易日的 `adjustment_factor` 真缺（个股级，非系统性），qfq 派生回滚。

## 与 155 股隔离清单的交集

- 原 155：136 恢复 + 19 仍隔离。
- **19 ∩ 74 = 10 只**：600058、600095、600107、600130、600156、600165、600169、600222、600360、600717（features 已 pinned 但分钟仍不可用）。
- 19 中另 9 只不在 74（600079、600114、600150、600153、600168、600191、600249、600323、600566）：不在修复宇宙内（NEEDS_REVIEW/POST_DIFF 类），features 未 pinned、分钟未重建——维持隔离。

## 15 只"features 完成但 Minute 未完成"（无任何 done key）

600058、600095、600107、600130、600156、600165、600169、600222、600360、600590、600717、603721、688689、002155、301117。
其中 10 只属于原 155 隔离集；另 5 只（600590、603721、688689、002155、301117）为 R2 修复完成但分钟派生终态缺口。**这 15 只日频研究可用、分钟级研究不可用**——资格矩阵中已分维度标注。

## 处理策略（不变）

- 不自动解封：features pinned ≠ 分钟资格恢复（P0-5 对抗测试 `test_factor_gap_blocked_asset_not_released_by_feature_pin` 覆盖）。
- `tradeability_at` 对缺口资产输出 `data_ready_minute=false` + `residual_factor_gap_minute`。
- 59 只备用源覆盖资产：分钟研究可用（akshare/eastmoney key），但 baostock 口径缺口留在矩阵中备查。
