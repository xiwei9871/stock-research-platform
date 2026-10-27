# M2-0 集成来源表

基线 `da7009bf`；分支 `release/r3-m2-preflight`。
全部远端 HEAD 已核验无漂移（main 9bd95562 / hotfix 9cd9e2c1 / p1d3 3ef96602 / p21 b7809cd6 / m1 a1c0be56 / m1-safety da7009bf）。

| target_file | source_branch | source_commit | method | conflict | test | release_track |
|---|---|---|---|---|---|---|
| src/.../eod_v2_writer.py | fix/r3-m1-deployment-safety | da7009bf | 已在基线；本轮 +`run_eod_v2_stage`、DSN 兼容 | 无 | E2E S1-S7 | M2-T |
| src/.../financial_version_store.py | 同上 | da7009bf | 已在基线；本轮 +乱序/回归分流、覆盖计数、head=max first_seen | 无 | finver F2-F8 | M2-F |
| src/.../data_integrity_gate.py | 同上 | da7009bf | 已在基线；本轮重写为需求声明式+按日校验+finver 分层 | 无 | acceptance 20/20 | 共用 |
| src/.../financial_ingest_integration.py | 新增（本轮） | — | raw RETURNING id + finver 同事务 | 无 | F5/F6 | M2-F |
| src/.../tradeability.py / core_data.py | main | 9bd95562 | 不修改，仅消费 | 无 | 既有 | M2-T 依赖 |
| scripts/m2_testdb_fixtures.py | 新增 | — | 独立实例 fixture | — | — | 测试基建 |
| scripts/m2_eod_e2e.py / m2_finver_e2e.py / m2_gate_acceptance.py / m2_backfill_drill.py | 新增 | — | 独立实例演练 | — | 全过 | 测试基建 |
| scripts/m2_t_backfill.py | 新增 | — | 受控回填执行器（checkpoint/续跑/限流） | 不替代 rehearsal 脚本 | B1-B4 | M2-T |
| sql/T1…sql / sql/F1…sql | 新增 | — | 未执行 DDL 包 | — | 测试库已执行 | M2-T / M2-F |
| tests/test_r3_m1.py | 同上 | da7009bf | +combine fail-closed 断言 | 无 | 47/47 | 共用 |
| P1d.3 迁移脚本/文档 | data/p1d3-v2-migration | 3ef96602 | **仅引用，不并入**（含无关运维改动） | — | — | 参考 |
| P2.1 取证/接口 | fix/r3-p21-financial-pit-shadow | b7809cd6 | 已在基线链上 | 无 | 23/23 | M2-F 依赖 |
| EOD hotfix wait-gate | hotfix/eod-dependency-wait-gate | 9cd9e2c1 | 已并入 main；V2 不改其逻辑 | 无 | — | 现状 |

## 兼容性核查（对 main@9bd95562）

- writer/stage 只 UPDATE v2 列，与 main 的 build/UPSERT 无交集；
- `daily_incremental` 调用点 = 建议接线处（同事务语义已核查）；
- `store_finance_payload_and_version` 不改动现有 `store_finance_payload` 签名，存量调用零影响；
- 无文件级冲突；两发布包无相互依赖。
