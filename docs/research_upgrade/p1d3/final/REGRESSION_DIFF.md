# P1d.3-final — 回归差集

基线：`fix/p1d2a-cutover-safety` @ `e6d6f5d4`（链含 `45d58083` 预演 + `425041b5` preflight + `34de8b0d` ops 杂务）

## 行为变化（生产默认路径影响：无）

| 面 | 变化 | 默认路径影响 |
|---|---|---|
| `compute_pit_limit_flags` | 输出新增 `shadow_state`/`old_is_limit_*`/`is_suspended` | 下游兼容 |
| `apply_pit_flags` | `qualification_state` 3→4 态（+`data_insufficient`），非 verified 统一 fail-closed | 仅 corrected 模式 |
| `load_vectorized_topn_inputs` | +`status_table` 参数（默认生产表，标识符校验）；verified_v2 SELECT 增 `limit_flags_version` | 默认等价 |
| `emit_v2_flags` | 新增守卫式纯 UPDATE 写入（缺 v2 契约列即 RuntimeError）；未接线 | 无 |
| `build_asset_status_daily` | +`emit_v2_target` 可选参数（同事务双写，默认 None=关闭；无界日期+开关→前置拒绝） | 默认不变 |
| `run_batch_safe` | 独立 commit、rollback-then-split、done 子批不重复算 | 仅预演 |
| 新脚本 | freeze/canary/eod-drill/failure-recovery/prodshape/diff-class | 新增 |

## 测试

- `tests/test_p1d3_migration_rehearsal.py`（8 例）+ p1d/p1d.1/p1d.2/p1d.2a 全套
- 13 个聚焦套件：**298 passed / 0 failed**（本轮无新增失败）
- 演练证据：MIGRATION_FREEZE / EOD_DUAL_WRITE / FAILURE_RECOVERY / V2_UPDATE_ROLLBACK / GRAY_GATE_CORRECTED / CANARY_GATE 全 PASS

## 隔离资产

- `p1d3_shadow.asset_status_daily_v2`（17.29M 回填比对源）、`migration_log`、`prod_replica`、`eod_replica`、`recovery_test`（后三者可 DROP）
- **生产表写次数：0**

