# P2.1-Final 回归差集

## 基线

`fix/r3-p21-financial-pit-shadow` @ `06b5abd6`，worktree `.worktrees/r3-p21`。

## 变更

- `financial_pit.py`：`operationally_available_at_asof` 恒 UNKNOWN（updated_at 不再用于双向推断）；`initial_version_provable` 入 evidence_trace；`historical_version_missing` 仅在 initial_public 且不可验证时触发；长滞后仅标 suspected_reannouncement 不反推初披日期。
- 新增 `scripts/p21_forensics_v2.py`（list[dict] 展开解析+字段级分类，替代 v1 错误口径）、`scripts/p21_consumer_shadow_v2.py`（两级语义+差异分类+真路抽样核验）。
- `tests/test_financial_pit_p2.py`：+6 例（解析器对抗×4、operational UNKNOWN、初版不可伪装）。

## 测试

`pytest tests/test_financial_pit_p2.py -q` → **23 passed / 0 failed**。
新增失败差集：**0**。

## 口径更正声明

- v1 forensics 分组键 15,720 与 metrics_changed=0 为**解析缺陷产物**，以 v2（930,620 键 / 34 变化）为准；
- v1 shadow 286,704 → v2 285,351（两级归并去重，差异归因已列）。
