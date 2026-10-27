# M2.0.1 Regression Diff — e73ef14 → fix/r3-m2-prelaunch-safety

## 代码

| 文件 | 变更 |
|---|---|
| `scripts/m2_t_backfill.py` | 重写：身份核验（conn.info 分类 prod/test/unknown）、prod 双重许可、默认 dry-run、checkpoint DDL 分离（ops_m2 契约检查）、全量对账（expected 集合+数据一致性）、stop-file+信号、WAL/磁盘水位、run_id+checksum |
| `src/.../data_integrity_gate.py` | +`evaluate_finver_writer`（新鲜度/raw 对账/范围绑定/链一致）；+`evaluate_eod_canary`+`v1_digest`；`evaluate_requirements` 输出 `satisfied`+未满足即 BLOCKED；finver DATA_READY 增加 raw 对账与范围条件 |
| `docs/.../preflight/FINAL_GATE.json` | 修复非法 JSON（生成器重写） |
| `tests/test_m2_release_artifacts.py` | 新增：JSON 合法性/必备文件/manifest 复算/状态一致性机器验收 |
| `scripts/m2_backfill_adversarial.py` | 新增 B5 对抗验收（15 案） |
| `scripts/m2_gate_final.py` | 新增 P0-C 验收（15 案） |
| `scripts/prod_backup_dryrun.sh` | 新增：分层备份命令模板（默认 dry-run） |
| `scripts/prod_readiness_check.py` | 新增：生产只读 pre-action 检查 |
| `docs/.../prelaunch/sql/ops_m2_checkpoint_schema.sql` | checkpoint 独立评审迁移 |
| `docs/.../prelaunch/*` | 15 份交付物 |

## 验证

- pytest：`test_r3_m1` + `test_financial_pit_p2` = **47/47**；`test_m2_release_artifacts`（见最终运行）
- 独立实例：gate acceptance **20/20**、backfill adversarial **15/15**、gate final **15/15**
- 恢复演练：独立实例 TABLE_RESTORE_VERIFIED（checksum 一致）；生产 RESTORE_NOT_VERIFIED 维持
- **新增失败差集：无**（evaluate_requirements 增字段不破坏既有语义；m2_gate_acceptance 20/20 复过）

## 行为变化说明

- `evaluate_requirements` 新增 `satisfied`/`reason` 键：combined 语义收紧——声明域未满足即 BLOCKED（此前只看聚合状态）；M1/M2 既有调用不传新字段时按原域评估，min_state 默认 data 与原 READY 语义一致。
- `evaluate_finver_writer` 为新增函数，无旧行为。
- backfill 执行器 CLI 契约变化（`--from/--to`→`--start/--end`、`--mode`、许可参数）：m2_backfill_drill.py（M2-0 历史演练）与新契约不兼容属预期——该演练已被 adversarial 套件取代。
