# Gate A：研究快照与正式发布一致性（只读调查 + 规则）

基线 `9bd95562`。数据库只读查询（按日期过滤，只取少量行），加上本地产物和代码。没有做任何写操作。

状态：`ROOT_CAUSE_IDENTIFIED / DESIGN_RULES_PROPOSED / NO_PRODUCTION_CHANGES`

## 1. 现象（RUNTIME_VERIFIED）

| 交易日 | manifest `review_evidence_snapshots` | `ops.review_item_snapshot` | EOD status 提交时间 | 快照首次写入时间 |
|---|---|---|---|---|
| 10-26 | skipped / 0 | 15 行 | 10-27 13:08:31 | 13:08:36 |
| 10-27 | skipped / 0 | 15 行 | 23:53:02 | 23:53:36 |
| 10-28 | skipped / 0 | 15 行 | 23:28:05 | 23:28:31 |
| 10-29 | skipped / 0 | 15 行（**15 行被改写过**） | 22:59:10 | 22:59:22，最后一次更新 23:00:12 |

这不是一次偶发，**每天都是这样**：manifest 记的是 skipped，表里却有 15 行，而且快照总是在正式发布提交之后才写入。

## 2. 根因

### 2.1 EOD 内部的快照步骤必然 skipped（SOURCE_VERIFIED）

1. `strategy_daily_eod` 先让 publisher 在 staging 目录里生成产物。publisher 拿到的 `manifest_upsert` 是 `manifest_entries.append`，只把记录攒在内存里，不写库（`strategy_daily_eod.py:280`）。
2. publisher 最后调用 `_write_review_evidence_snapshot_entry`（`strategy_eod_publish.py:381`），进而调用 `run_eod_review_evidence_snapshots`，后者内部用 `build_review_queue(use_strategy_snapshots=False)` 去读**数据库里当日的正式 manifest**。
3. 可是这时候 manifest 还没提交。提交发生在 publisher 返回之后的 `commit_strategy_publication`（`strategy_daily_eod.py:436`）。
4. 于是 review queue 返回 `exact-date official strategy manifest unavailable`，队列为空，状态记为 `skipped`、0 行。这条记录随后和其他 manifest 一起被提交进库（10-29 的 warnings 原文就是这两句）。

所以 EOD 自己从来没有写过快照。manifest 上的 skipped 如实记录了 EOD 内部那一步的结果，只是这个结果因为执行顺序问题本来就不可能成功。

### 2.2 快照实际由修复流程写入，而且没有回写 manifest（RUNTIME + SOURCE_VERIFIED）

- 10-29 的修复产物 `eod_auto_repair/2026-10-29/`（内部路径）显示：修复检查发现 `review_evidence_snapshots` 为 skipped/0，于是执行 `repair_review_evidence_snapshots`，时间是 15:00:10 到 15:00:12 UTC（即 23:00:10–12 CST），结果 success，写入 15 条快照和 15 条摘要。
- 修复时传入的 `run_id` 是 `eod-auto-repair-snapshots-2026-10-29`（`eod_auto_repair.py:1834`）。但 `_queue_payload_with_run_context` 会优先保留条目里已有的 `run_id`（`review_evidence_snapshots.py:452`），而这时 review queue 已经能读到已提交的 manifest，条目自带 `strategy-eod-2026-10-29-local`。所以快照行上记的是 EOD 的业务 `run_id`，看不出来其实是修复流程写的。
- `repair_review_evidence_snapshots`（`eod_auto_repair_actions.py:360`）只返回动作结果，**不写 manifest**。所以 manifest 一直停在 skipped。
- 10-29 的 15 行"首次写入 22:59:22，改写 23:00:12"：23:00:12 是修复流程那次写入。22:59:22 那次是谁写的，还没确定（NOT_VERIFIED）。可能是另一次修复或就绪检查的调用，因为修复锁文件的时间是 22:59:30，非常接近。由于快照表是 `ON CONFLICT (run_id, digest_key) DO UPDATE`，第一次写入的内容已被覆盖，**无法还原**。

### 2.3 这些快照代表正式发布吗？

推断有条件成立（INFERRED，证据较强）：快照是在正式提交之后，由 `build_review_queue` 从**已提交的** `review_queue_strategy_manifest` 生成的，内容来源就是正式发布的结果。

但目前没有任何字段能证明这一点：没有 attempt 关联，没有产物哈希关联，manifest 状态又是错的，第一次写入的内容也已被覆盖。所以按你的要求，`lead_timeline` 可以展示这些记录，但**不能标为 `official`**，应当标为 `publication = derived_after_publish, verification = unverified`。

## 3. Gate A 规则（DESIGN）

### 3.1 快照只能在正式发布提交之后生成，并且要登记

- 把快照步骤从 publisher（staging 阶段）移到 `commit_strategy_publication` + `handle.commit()` 成功之后，作为发布后的一个步骤，由 EOD 自己调用。
- 这一步单独写一行 manifest（`module=review_evidence_snapshots`），带上 `attempt_id` 和 `source_manifest_sha256`（即 `review_queue_strategy_manifest.csv` 的 sha256）。
- 修复流程也走同一个函数，并且**必须回写 manifest**，`trigger=repair`。

### 3.2 快照不再覆盖历史

- `ops.review_item_snapshot` 的冲突键从 `(run_id, digest_key)` 改为 `(run_id, digest_key, payload_hash)`：内容相同就幂等跳过，内容不同就新增一行，并记录 `attempt_id`。
- 读取时取每个 `(run_id, digest_key)` 的最新一行作为当前版本，历史行全部保留。
- 这一步需要改约束，要在隔离实例上先验证。

### 3.3 `official` 的判定规则（读取方使用）

一条快照只有同时满足以下全部条件，才能标为 `official`：
1. 它的 `run_id` 在 `ops.strategy_daily_eod_status` 中当日为 `success`；
2. 它记录了 `attempt_id`，并且该 attempt 的状态是 `published`；
3. 它的 `source_manifest_sha256` 与正式发布的 `review_queue_strategy_manifest.csv` 一致；
4. 它的创建时间晚于 status 的提交时间。

历史数据不满足第 2、3 条，统一标为 `derived_after_publish / unverified`，不做回填伪造。

### 3.4 attempt 生命周期（采纳你的建议）

- 每次执行在开始时插入一行 attempt，状态为 `running`，并且**在发布事务之外单独提交**。这样即使发布事务失败，这次尝试的记录也已经在库里。
- 结束时把这一行更新为终态：`published / failed / skipped`，同时写入 `failure_class`。
- 不同的 attempt 之间永远不会互相覆盖。这张表不叫"只追加表"，而是"按 attempt 不可覆盖"。
- 本地兜底文件 `run_record_<attempt_id>.json`：先写临时文件，再 `os.replace` 原子替换。数据库不可用时只写这个文件，恢复后由修复流程补插记录（按 `attempt_id` 幂等）。
- 进程异常退出、attempt 停在 `running` 的情况，由下一次执行或修复流程检测，并把它标为 `failed`（`failure_class = abandoned`）。

### 3.5 通知幂等

- 幂等键：`(run_id, channel, payload_sha256)`。同一份内容发到同一渠道只发一次，重试会复用同一个 `delivery_id`，并累加 `attempt_count`。
- 只有内容变了（例如修复后重发），才算一条新的投递。

## 4. 隔离环境验证（在 Gate A 实施时进行）

| 测试 | 期望 |
|---|---|
| 同日运行两次 | 两条 attempt 都保留；manifest 指向最后一次；快照内容相同时不新增行，不同时新增一行，旧行保留 |
| 发布事务失败回滚 | attempt 记为 `failed`，不产生快照，manifest 不变 |
| 数据库不可用 | 只写本地 `run_record_<attempt_id>.json`；恢复后补插，补插两次结果一样 |
| 修复流程补快照 | 回写 manifest，`trigger=repair`；快照带上修复那次的 `attempt_id` |
| 历史数据读取 | 10-26 至 10-29 的快照显示为 `derived_after_publish / unverified`，不显示为 `official` |

## 5. 对修正案的影响

- DESIGN_REVIEW_AMENDMENT_V02 §3 写的是"第一数据源是 `review_item_snapshot`"，这一点仍然成立。但要加上 §3.3 的 official 判定规则，历史记录不能直接当作正式结果。
- §1 的 attempt 设计改为 §3.4 的生命周期（允许单行状态流转，attempt 之间不可覆盖，开始记录在发布事务之外提交）。
- §2 的通知设计加上 §3.5 的幂等键。
