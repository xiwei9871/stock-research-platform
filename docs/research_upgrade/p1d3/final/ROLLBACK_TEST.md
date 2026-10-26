# P1d.3 — 回滚演练汇总

三处回滚证据均通过，覆盖任务要求的全部回滚形态：

| 形态 | 演练 | 结果 | 证据 |
|---|---|---|---|
| 批次中断恢复 | `run_batch_safe` + 真实 UndefinedTable 注入 | abort→rollback→二分→checksum 复原；resume 零重算 | `FAILURE_RECOVERY.json` |
| 列级回滚 | `prod_replica` 全量 v2 列置 NULL | checksum 回到更新前空镜像；v1 checksum 三次校验不变 | `V2_UPDATE_ROLLBACK.json` |
| 部分提交 | `statement_timeout=50ms` 注入 QueryCanceled | 中止批 0 行残留；已提交批不受影响 | 同上 |
| EOD 中断 | 同日双写事务内注入异常 | v1+v2 整日回滚，无半批 | `EOD_DUAL_WRITE.json` |
| 读路回滚 | `qualification_mode` 参数回退 | 纯参数切换，无数据变更，可逐消费者回退 | `GRAY_GATE_CORRECTED.json` |
| DDL 回滚 | additive 列 `DROP COLUMN` | 秒级；不触既有列 | runbook A |

生产执行时的回滚命令逐一列于 `MIGRATION_RUNBOOK.md` / `PRODUCTION_RUNBOOK.md` 各步骤。
