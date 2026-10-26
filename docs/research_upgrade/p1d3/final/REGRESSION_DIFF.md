# P1d.3-final — 回归差集

基线：`fix/p1d3-migration-rehearsal` @ `45d58083`

## 行为变化（生产默认路径影响：无）

| 面 | 变化 | 默认路径影响 |
|---|---|---|
| `emit_v2_flags` | `INSERT..ON CONFLICT` → **纯 UPDATE**（VALUES join）。原因：Postgres 在冲突仲裁前先校验 proposed row NOT NULL——生产形态表上必炸；且 status 行必已存在 | emit 仍守卫+未接线 |
| `verified_v2` SQL | SELECT 增 `limit_flags_version`；纳入 v2 契约探测集（缺列→全 missing，非 SQL 错） | 模式未启用 |
| `run_batch_safe` | 独立 commit 'running' 标记、异常先 rollback 记 `failed_split` 再二分、done 子批不重复算、`migration_log` 加 range/error 列 | 仅预演脚本 |
| `p1d3_gray_read_check.py` | 门禁化：异常/空集→FAIL、FULL OUTER 键集对比、flag+rule_id+version 一致性、md 由同批 JSON 生成 | 仅脚本 |
| 新脚本 | `p1d3_failure_recovery_test.py`、`p1d3_prodshape_rollback_test.py`、`p1d3_diff_classification.py` | 新增 |

## 测试

- `tests/test_p1d3_migration_rehearsal.py` +2（log 全 done 断言、纯 UPDATE 不插入语义）
- 13 个聚焦套件：见 FINAL_GATE
- 演练级证据：FAILURE_RECOVERY.json、V2_UPDATE_ROLLBACK.json、GRAY_GATE_CORRECTED.json

## 隔离资产

- `p1d3_shadow.asset_status_daily_v2`（17.29M，保留作回填比对源）
- `p1d3_shadow.prod_replica`（演练副本，审批后可 DROP）
- `p1d3_shadow.recovery_test`（演练，可 DROP）
- **生产表写次数：0**
