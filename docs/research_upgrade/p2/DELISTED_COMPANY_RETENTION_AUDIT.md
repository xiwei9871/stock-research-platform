# 退市公司财务历史留存审计

## 范围

`core.asset_master` 中 `delist_date IS NOT NULL`：**13 家**（全部为 2026-06/07 月退市——平台 5,213 universe 内的近期退市；更早历史退市证券不在 universe 口径内）。

## 结果

| 检查 | 结果 |
|---|---|
| 退市后 finance 三表历史是否保留 | ✅ 13/13 保留 income 历史（含 balance/cf），按退市日分组全部 with_income=with_balance=with_cf=1 |
| 退市股历史记录能否经 financial_pit_at 查询 | ✅ 实测 edge case `delisted_history_queryable` → verified_public |
| 退市后是否继续被抓取/覆盖 | 2026-06-30 期 balance+cf 双缺 14 家中有 13 家=近期退市股，EM 接口退市后不再提供 → 最后一期停在 2026-03-31（见 Q2 对账） |
| 存活偏差 | universe 以 asset_master 为准；更早退市但从未入 universe 的证券**不可见**（属覆盖缺口而非删除） |

## 结论

- 现有退市股**历史披露数据未被删除**，PIT 查询正常——Gate 通过；
- 风险：EM 接口退市即断供 → 退市前最后一期若有重述也不会再被捕获（版本冻结在退市时点）；
- 建议：修复阶段对 13 家退市股做 raw payload 最终归档（hash 快照），标记 `source_unavailable_delisted`，防止后续误判为"应更新未更新"。
