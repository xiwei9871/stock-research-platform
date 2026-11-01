# M2-0 Regression Diff — da7009bf → release/r3-m2-preflight

## 代码变更

| 文件 | 变更 |
|---|---|
| `eod_v2_writer.py` | +`run_eod_v2_stage`（独立事务、written/idempotent 才 commit、其余显式 rollback）；DSN 兼容 |
| `financial_version_store.py` | +乱序/回归分流（`late_arrival_repeat`/`reversion`/`arrived_out_of_order`）；head=max first_seen；`read_as_of`/`latest` 按 first_seen 排序；D2 覆盖计数；`finver_event_fp_idx`/`observation_seen_idx` |
| `data_integrity_gate.py` | 需求声明式 `evaluate_requirements`；`evaluate_tradeability` 按日维度校验（NULL/混版/异版/缺 rule_id/无效状态）；`require_v2`+`expected_version` 强制；`evaluate_finver_schema` 三层（SCHEMA/WRITER/DATA_READY）；`combine` 空输入/未知 token→BLOCKED |
| `financial_ingest_integration.py` | 新增：raw INSERT RETURNING id + `ingest_payload` 同事务 |
| `scripts/` | +m2_testdb_fixtures、m2_eod_e2e、m2_finver_e2e、m2_gate_acceptance、m2_backfill_drill、m2_t_backfill |
| `tests/test_r3_m1.py` | combine() 空输入断言 READY→BLOCKED（契约升级），+未知 token 断言 |

## 测试

- `test_r3_m1.py` 24 + `test_financial_pit_p2.py` 23 = **47 passed / 0 failed**
- 独立实例演练：EOD E2E **9/9**、finver **7/7**、gate acceptance **20/20**、backfill **4/4**
- **新增失败差集：无**（唯一变更断言属契约升级的既定修正）

## 行为变更说明

- `combine()` 空输入 READY→BLOCKED：fail-closed 修正，唯一调用方为本模块评估路径；
- `evaluate_tradeability` 默认参数保持向后兼容（不传 require_v2 时与原语义近似，报告更细）；
- finver ingest 计数键变更（`new_version`/`identical_bump` 保留，新增 processed/changed/reversion/late_arrival_repeat/arrived_out_of_order/missing_period/unknown_source/failed）——M1 演练脚本沿用旧键名仍兼容。
