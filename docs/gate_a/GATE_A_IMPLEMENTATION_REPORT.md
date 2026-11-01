# Gate A 实施与隔离测试报告

- 分支：`fix/gate-a-snapshot-publication-consistency`，基线 `origin/main` = `9bd95562`
- 设计依据：PR #19 `docs/architecture_audit_v02/GATE_A_SNAPSHOT_CONSISTENCY_V02.md` 和修正案
- 状态：`GATE_A_IMPLEMENTED / ISOLATED_TESTS_PASS / AWAITING_PRODUCTION_APPROVAL`
- 范围：只做 Gate A，不含 Gate B（研究线索与 API）和 Gate C（通知与 UI）。没有执行生产 schema 迁移，也没有部署。

## 1. 改动

| 文件 | 内容 |
|---|---|
| `src/stock_research/run_attempts.py`（新） | `ops.data_run_attempt` 的 DDL；`DbAttemptStore`：开始记录单独提交，数据库不可用时原子写入 `run_record_<attempt_id>.json`；`MemoryAttemptStore` 供测试用；`backfill_local_records`（可重复执行，结果相同）；`mark_abandoned`；`latest_published_attempt`。attempt 一旦进入终态就不再更新 |
| `src/stock_research/strategy_daily_eod.py` | 每次执行生成一个 publication attempt（`module=strategy_daily_eod_publication`，记录 trigger 和 git SHA）。依赖阻塞、计算失败、发布事务失败都会把 attempt 标为失败并写明 `failure_class`。只有发布提交成功后才调用 `run_post_publish_snapshots`，传入本次 canonical `review_queue_strategy_manifest.csv` 的 sha256。manifest 的 metadata 带 `publication_attempt_id`。attempt store 和快照函数都可以注入 |
| `src/stock_research/strategy_eod_publish.py` | 去掉 publisher 内部在提交前做快照的那一步 |
| `src/stock_research/review_evidence_snapshots.py` | `snapshot_id = f(run_id, digest_key, payload_hash)`。写入改为 `ON CONFLICT (run_id, digest_key, payload_hash) DO NOTHING`，不再覆盖。新增来源列 `publication_attempt_id / snapshot_attempt_id / source_manifest_sha256`。新增 `*_current` 视图：取每个 run 最近一批发布，同批内每个条目取最新一行，不会把两次发布的结果混在一起。`run_post_publish_snapshots` 是 EOD 和修复共用的入口：固定读取源文件，校验哈希，核对源文件行数，执行期间检测源文件是否被替换，回写 manifest（使用调用方传入的 `service`）。新增 `snapshot_official_status`，把"是否正式发布"和"是否已验证"分成两个维度 |
| `src/stock_research/eod_auto_repair.py` | 修复快照改为走 `run_post_publish_snapshots`（`trigger=repair`），关联到最近一次 published 的 publication attempt，并且必须回写 manifest |
| `src/stock_research/eod_auto_repair_actions.py` | 修复结果状态由实际返回值决定（success / degraded / skipped / failed），不再固定写 SUCCESS |
| `research_case_seed.py` / `research_evidence_backfill.py` / `research_evidence_registry.py` | 读取改为 `*_current` 视图，旧的读取语义不变（每个条目只返回一行） |
| `tests/conftest.py`（新） | 测试期间默认禁止 `psycopg.connect`。只有 `STOCK_RESEARCH_TEST_DB_SERVICES` 中列出的隔离服务可以连接 |
| `deploy/migrations/gate_a_001_forward.sql` / `_rollback.sql`（新） | 正向迁移和回退脚本 |

## 2. 测试结果

| 测试 | 结果 |
|---|---|
| `tests/test_gate_a_snapshots.py`（新，19 个） | 全部通过 |
| `tests/test_strategy_daily_eod.py`（含新增 Gate A 测试 4 个） | 65 个通过 |
| 相关旧测试：`test_strategy_eod_publish`、`test_eod_auto_repair*`、`test_data_run_manifest`、`test_research_evidence_registry` | 220 个通过（含上一行） |
| `tests/integration/test_gate_a_snapshot_versioning_postgres.py`（新，3 个） | 在本机临时创建的独立 PostgreSQL 16.14 实例上通过（unix socket，单独端口，测试结束后删除 schema）。没有连接任何共享数据库 |
| 全量单元测试 | Gate A 分支与 `main` 对比的结果见 §2.1 |

连接阻断还发现了 3 个旧测试会连接真实数据库，`main` 上同样如此：`test_official_runner_rejects_output_root_outside_explicit_release`、`..._symlink_escape`、`test_mid_trend_review_uses_latest_signal_score_for_continued_holdings`。这次已在测试内部把相关调用替换掉。

### 2.1 全量回归

两边都在启用 `tests/conftest.py` 连接阻断的情况下运行，命令为 `pytest tests --ignore=tests/integration --continue-on-collection-errors`。

| | Gate A 分支 | `main`（`9bd95562`，临时放入同一份 conftest） |
|---|---|---|
| 全量 | 3406 passed / 316 failed / 113 errors / 4 skipped | 只对分支上失败的 316 个用例所在文件重跑：317 failed |
| 失败用例集合 | 316 个 | 与分支完全相同，另多 1 个：`test_platform_ready_scripts.py::...[2-TERM]`，是信号时序相关的偶发失败 |
| 收集错误（113 个） | `watchdog_runner.backfill` 导入失败（本机外部包问题） | 完全相同 |

结论：**Gate A 没有引入新的失败用例**。这 316 个失败在 `main` 上同样存在，原因有两类：一类是测试本身依赖本机环境，另一类是有 16 个以上的用例原本就会连接真实数据库，现在被阻断拦下。这些都不在本 PR 范围内，但说明连接阻断会让一批旧测试暴露出来。所以本 PR 建议先合并阻断，再分批修复这些旧测试；如果暂时不希望全局阻断，也可以只在 Gate A 相关测试中启用。待决定。


### 2.2 覆盖的验收场景

| 场景 | 测试 |
|---|---|
| 同一天两次正式发布，两条 attempt 都可追溯 | `test_gate_a_same_day_two_publications_keep_both_attempts_and_bind_snapshots` |
| 第二次发布内容不同时，快照绑定 B，不读 A | 同上，加 `test_snapshot_refuses_a_different_published_version`、`test_snapshot_detects_source_replaced_during_run`，以及集成测试中的 current 视图不混批次 |
| 发布失败回滚后，旧的正式版本不受影响 | `test_gate_a_failed_publication_records_attempt_and_keeps_previous_release` |
| 数据库不可用时，本地 attempt 记录可以恢复 | `test_db_attempt_store_falls_back_to_local_record`；集成测试 `test_attempts_persist_backfill_and_abandon`（补录两次结果一致，终态不会被改写） |
| 修复后 manifest 与实际写入数量一致 | `test_snapshot_binds_publication_attempt_and_source_hash`、`test_snapshot_reconciles_written_count_with_source`、`test_repair_status_follows_real_result` ×5 |
| repair attempt 与 publication attempt 分开记录 | `test_repair_and_publication_attempts_are_separate` |
| 历史快照保持 unverified | `test_official_requires_version_proof`；集成测试中旧行迁移后 `publication_attempt_id` 为 NULL |
| 旧 API 和 Dashboard 查询兼容 | `list_review_item_snapshots` 和 `load_evidence_digest_snapshot` 在集成测试中通过；3 个研究模块的旧测试通过 |
| 测试不依赖生产库 | `tests/conftest.py` 连接阻断；`test_default_manifest_writer_uses_caller_service` |

## 3. 数据库迁移与回退

**正向**（`deploy/migrations/gate_a_001_forward.sql`，单个事务，可以重复执行）：
1. 新建 `ops.data_run_attempt` 和索引。
2. 在两张快照表上加 3 个可为空的来源列（不带默认值，只改元数据，不重写表）。
3. 去掉 `UNIQUE (run_id, digest_key)`，建立 `UNIQUE (run_id, digest_key, payload_hash)`。在 10-29 的规模下每张表约几百到几千行，建索引是秒级。
4. 建立 `*_current` 视图。

已有行全部保留，`snapshot_id` 不变，来源列为 NULL，因此会被判定为 unverified。

**发布顺序**：
1. 先对 `ops.review_item_snapshot`、`ops.evidence_digest_snapshot`、`ops.data_run_manifest` 做表级 dump。
2. 执行迁移。
3. 部署代码。

代码必须在迁移之后部署，因为新代码依赖新的唯一约束和视图。如果顺序反了，写入会因为缺少约束而报错，旧数据不会被改动。

**回退**（`deploy/migrations/gate_a_001_rollback.sql`）：
1. 删除视图。
2. 每个 `(run_id, digest_key)` 只在原表保留最新一行，其余版本移到 `*_version_archive` 表，不删除。
3. 恢复原来的唯一约束。

来源列和 `ops.data_run_attempt` 保留，旧代码不会读取它们。代码回退到 `main` 后即可恢复原来的行为。集成测试已验证回退后行数守恒，旧约束重新生效。

## 4. 未解决与待处理

| 项 | 状态 |
|---|---|
| 生产迁移和部署 | 等待批准 |
| 22:59:22 那次快照写入的来源 | 已被覆盖，无法确认，历史数据保持 unverified |
| 开发期间误写的 4 条生产 manifest 记录 | 待处理，见 §5 |
| `tests/test_*` 中因 `watchdog_runner` 导入失败而无法收集的模块 | 在 `main` 上同样存在，与本 PR 无关 |
| GitHub Backend CI 遗留的 `tushare` 导入问题 | 由 Devin 处理，不在本 PR 范围 |

## 5. 待处理事项：开发期间误写的 4 条生产 manifest 记录

2026-11-01 21:12，一次开发测试把以下 4 行 `ops.data_run_manifest` 的可变字段改写了：status 仍是 skipped，row_count 仍是 0，但 warnings、metadata、config_version（v1 改成了 v2）、ended_at、artifact_path、error_message 被覆盖，`updated_at` 变成 2026-11-01 21:12。

| manifest_id |
|---|
| `strategy-eod-2026-06-24-local:review_evidence_snapshots:eb2cc7b92409` |
| `strategy-eod-2026-07-02-local:review_evidence_snapshots:bb5808244588` |
| `strategy-eod-2026-07-24-local:review_evidence_snapshots:d704ac8fbdef` |
| `strategy-eod-2026-08-06-local:review_evidence_snapshots:556e1b6b1c9b` |

- **已知影响**：metadata 里出现了不存在的 attempt_id 和测试生成的哈希；config_version 不再准确。这些都是 skipped 状态的历史行，复盘队列和 EOD 判定都不读这个模块。是否还有其他影响：NOT_VERIFIED。
- **可靠原值来源**：10-28 L2 全库备份中这 4 行的原值。修正时只写回这 4 行的可变字段。如果从备份中取不到原值，就在 metadata 中加标记 `{"integrity": "overwritten_by_dev_test_2026-11-01"}`，让这种不确定状态保持可见。
- 是否修正、何时修正需要单独批准，不在本 PR 中执行。
