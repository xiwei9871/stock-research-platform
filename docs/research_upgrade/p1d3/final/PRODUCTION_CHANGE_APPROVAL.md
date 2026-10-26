# P1d.3 — 生产变更审批单（提交审批用）

## 申请范围

按 `MIGRATION_RUNBOOK.md` 六个检查点分步授权执行 V2 迁移。每检查点独立签字；任一步不通过即停。

## 变更清单

| # | 变更 | 副作用 | 回滚 | 已演练证据 |
|---|---|---|---|---|
| 1 | `ALTER TABLE` +5 v2 列 | 元数据级 | DROP COLUMN | prod_replica |
| 2 | EOD `emit_v2_target` 接线 | +5k 行/日 UPDATE，同事务 | 移除参数 | EOD_DUAL_WRITE.json |
| 3 | 17.29M 历史回填 | ~20min、~4–5GB WAL、行锁 | 列级置 NULL | 影子全量 + prodshape |
| 4 | 消费者 `qualification_mode` 灰度 | 只读切换 | 参数回退 | GRAY_GATE + CANARY |
| 5 | 回测/情绪重验收 | 产物层 | 不发布即回滚 | shadow 方法论 |

## 风险声明

- **WAL**：全表回填 ~4–5GB WAL——执行前必须验证归档/复制余量（预检查已列）；
- **WAL 放大点**：UPDATE 每行产生新 tuple，表膨胀 ~等量数据页，执行后需 `VACUUM (ANALYZE)` 评估（低峰）；
- **v1 持续误标**：双写期 v1 仍由旧阈值写入——已知并接受，verified_v2 切换后失效；
- **不可自动修复集**：rule_unknown 5 行（1990-12-19 ST 异常）、data_insufficient 387,314 行、北交所 ST 未核实——保留 UNKNOWN 不填补；
- **emotion 下游**：`market_emotion_state_v1` 依赖 v1 计数，列于 NEEDS_REVALIDATION，不随本次切换。

## 审批决定（留空待签）

- [ ] 检查点 1 DDL 窗口：______
- [ ] 检查点 2 EOD 接线：______
- [ ] 检查点 3 回填窗口与 WAL 确认：______
- [ ] 检查点 4 消费方顺序：______
- [ ] 检查点 5 重验口径：______
