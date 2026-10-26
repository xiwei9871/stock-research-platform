# P1d.3 — 回归差集

基线：`fix/p1d2a-cutover-safety` @ `e6d6f5d`

## 行为变化

| 面 | 变化 | 生产默认路径影响 |
|---|---|---|
| `compute_pit_limit_flags` | 输出新增 `shadow_state`（0/1/2/3 枚举）、`old_is_limit_up/down`、`is_suspended` 列 | 无——下游 `apply_pit_flags` 兼容有无该列 |
| `apply_pit_flags` | `qualification_state` 由 3 态扩为 4 态：新增 `data_insufficient`（有规则但缺 bar 数据） | 无——`!= verified` 仍统一 fail-closed；既有测试断言集已扩 |
| `load_vectorized_topn_inputs` | 新增 `status_table` 参数（默认 `core.asset_status_daily`，标识符校验） | 默认值不变则 SQL 等价 |
| `core_data.py` | 新增 `emit_v2_flags`（守卫式 V2 增量写入） | 无——不接线任何生产调用，且目标表无 v2 列时自拒绝 |
| `scripts/` | +`p1d3_migration_rehearsal.py`、+`p1d3_gray_read_check.py` | 新脚本，无既有路径改动 |

## 隔离数据资产

- `p1d3_shadow.asset_status_daily_v2`：17,294,002 行（v1 拷贝 + v2 flags + rule_id + version + batch_id）
- `p1d3_shadow.migration_log`：37+ 批 checkpoint
- **均为隔离 schema；`core.asset_status_daily` 未被写入一行。**

## 测试

- `tests/test_p1d3_migration_rehearsal.py`（5 例：emit 守卫×2、status_table 校验、四态合成、灰度读真库）
- 13 个聚焦套件重跑：**296 passed / 0 failed**
- `test_legacy_vs_corrected_diff_explainable` 断言集扩展至 4 态（唯一预期内测试改动）
