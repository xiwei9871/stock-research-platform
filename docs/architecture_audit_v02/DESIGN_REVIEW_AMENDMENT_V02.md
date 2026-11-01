# V0.2 设计评审修正案

针对 PR #19 评审意见的四项修正。基线 `9bd95562`。本文只修正设计，不进入开发。数据库核对使用只读事务，只查少量按日期过滤的行。

状态：`DESIGN_AMENDED / AWAITING_IMPLEMENTATION_APPROVAL / NO_PRODUCTION_CHANGES`

## 1. 运行身份：区分业务运行与执行尝试（修正 R1）

**事实**（SOURCE_VERIFIED，`data_run_manifest.py:124-168,315-318`）：
- `manifest_id = f"{run_id}:{module}:{sha1(run_id|module|source)[:12]}"`。
- 写入是 `ON CONFLICT (manifest_id) DO UPDATE`，会覆盖 status、error、artifact_path、code_version、metadata 等字段。
- EOD 的 `run_id` 按交易日固定为 `strategy-eod-{date}-local`。

所以同一天同一模块的第二次运行会**覆盖**第一次的结果。只在 metadata 里加 `attempt_id` 解决不了，你的判断是对的。上一版 R1 的设计是错的。

**修正设计**：

| 标识 | 含义 | 存放 |
|---|---|---|
| `run_id`（不变） | 业务运行：某交易日的正式 EOD。Dashboard 和 review queue 现在用它关联，保持兼容 | `ops.data_run_manifest`，当前状态 |
| `attempt_id`（新增） | 一次执行：定时、手动补跑或故障重试，用 UUID | 新表 `ops.data_run_attempt`，**只追加** |

- `ops.data_run_attempt(attempt_id PK, run_id, module, source, trigger, started_at, ended_at, status, failure_class, git_sha, input_refs jsonb, artifact_path, error_message, created_at)`：每次执行插入一行，从不更新。
- 现有 manifest 表照常 upsert，表示"该业务运行的当前状态"，同时在 metadata 里记下 `last_attempt_id`。读取方不需要任何改动。
- 两者在 `commit_strategy_publication` 的同一个事务里写入。数据库不可用时，`run_record.json` 用同样结构写到本地，恢复后补插 attempt 行（R3 不变）。
- `failure_class` 取值：`dependency / environment / compute / publish / notify`。`status` 继续沿用现有枚举。

这是一张新表，但只是现有台账的执行历史，不是新的任务系统。

## 2. 通知状态：不进入 manifest 的 status（修正 R5）

**事实**：`ops.data_run_manifest.status` 的 CHECK 约束只允许 `success / partial / skipped / failed / unavailable`（`data_run_manifest.py:28`）。上一版写 `delivered` 会违反这个约束。

**修正设计**：通知结果单独记录，作为 attempt 的下游。

`ops.notification_delivery(delivery_id PK, run_id, attempt_id, channel, payload_ref, payload_sha256, generated_at, platform_accepted_at, platform_message_id, delivery_status, error, user_ack_at)`

`delivery_status` 分四个阶段，各自单独记录，不合并成一个值：

| 阶段 | 字段 | 现在能否取得 |
|---|---|---|
| 消息生成 | `generated_at` + `payload_sha256` | 能 |
| 平台接受 | `platform_accepted_at` + `platform_message_id` | 取决于发送方式：直接调用飞书 API 能拿到；经过调度器 announce 时需要读它的投递状态（NOT_VERIFIED 是否有消息 ID） |
| 送达用户 | — | 飞书一般只确认平台接受，**不保证送达**，记为 NOT_AVAILABLE |
| 用户已读或已处理 | `user_ack_at` | 由用户在 Dashboard 点"已看"或执行复核动作时写入 |

**消息内容改为确定性生成**：
- 由发布后的结构化产物生成消息正文：`review_queue_strategy_manifest` 加上 `ops.strategy_daily_eod_status`。
- 正文至少包含交易日、`run_id`、各策略状态，以及每个候选的股票、来源策略、排名、触发原因和 Dashboard 个股链接。
- LLM 只能在这份正文之外补充说明，不能负责组织内容，也不能负责投递。
- 调度器任务改为执行确定性的发送脚本。它的 stdout 只用于运维告警，不再作为研究通知的内容。

## 3. Research Lead 必须覆盖真实策略候选（修正方案 C 的数据源）

**新发现**（RUNTIME_VERIFIED）：10-29 的策略候选**已经入库**。
- `ops.review_item_snapshot` 中，10-26 到 10-29 每天各有 15 行，3 个策略各 5 行。
- 每行带 `run_id = strategy-eod-{date}-local`、`source_name`、`source_rank`、`evidence_status`、`review_item_payload`。
- 全链路审计用的样本（Tech Bottleneck 当日排名第 1）就在其中，`evidence_status = PARTIAL`。
- 写入方是 `review_evidence_snapshots.py`。

所以方案 C 的第一个数据源应该是 `ops.review_item_snapshot`，不是另外读 CSV。上一版列的"4 个来源"其实已经包含了它，但报告没有写明它覆盖真实策略候选，这一点需要更正。

**同时发现一处台账不一致**（RUNTIME_VERIFIED）：
- 10-29 manifest 中 `review_evidence_snapshots` 模块记为 `skipped`，`row_count = 0`。
- 但表里当天实际有 15 行。

这说明 manifest 对这个模块的状态不能当作事实使用。根因需要单独排查（NOT_VERIFIED：可能是先写快照、后由另一个路径把 manifest 标为 skipped）。

**覆盖边界**：
- snapshot 只包含每个策略的前 5 名，也就是 review queue 的内容。
- Tech Bottleneck 当日的完整候选池（`tech_bottleneck_daily_candidates`，约 2.5 万行）不在其中。
- 第一阶段只覆盖"已发布的复核候选"；完整候选池通过 `artifact_path` 引用，不复制进数据库。

**验收标准（采纳你的表述）**：给定 10-29 真实候选的 `asset_id`，`GET /api/assets/{asset_id}/leads` 必须返回以下内容，并且能从这条线索直接加入观察池：
- 来源策略
- 交易日
- `run_id`，以及第 1 节的 `attempt_id`
- 排名与触发原因（来自 `review_item_payload`）
- 证据状态
- 产物链接（`artifact_path`）
- 后续状态：复核、观察池、决策
- 通知记录（第 2 节）

## 4. 财务 PIT 不一致：降级为独立差异审计

**核对结果**（SOURCE_VERIFIED）：
- `midtrend_pit_fundamental_features.py:139` 用 `announcement_date > trade_date` 判断前视，即公告当天可用。
- 这个模块只被 `cli.py` 和 4 个研究模块（`midtrend_*_attribution_v1`、`midtrend_daily_review_lite_*` 等）引用，**不在每日 EOD 发布路径上**。
- 因此它影响的是研究归因结论，不影响每日发布的候选。

**设计**：单独做差异审计，不在这一阶段修改规则。
1. 在研究层同时用两种口径计算同一组样本：`legacy`（当天可用）和 `financial_pit`（D+1）。
2. 输出受影响的样本数量、日期和资产，以及受影响的归因结论。
3. 旧结果保留并打上版本标记；只有确认影响后，才决定是否切换。

## 5. 其他修正

- **`provenance` 拆成独立维度**，不再用一个 `status` 表示所有含义：
  - `publication`：`official / experimental`
  - `data_origin`：`real / fixture / mock`
  - `freshness`：`current / stale`，附 `as_of` 和预期日期
  - `degradation`：`none / fallback / partial`，附原因
  - `run_id` 和 `attempt_id`
- **币种不允许默认 CNY**：无法确定时写 `UNKNOWN`。A 股可以由交易所映射出 CNY，但必须由代码显式映射，不能靠列默认值。
- **磁盘约 78GB 余量**（USER_STATED）：第一阶段只新增两张小表和读取 API，不做任何批量重写，不与存储治理同时进行。

## 6. 第一阶段：最小闭环（替代原阶段 1、2 的拆分）

一个真实场景（10-29 或之后某天的已发布候选），贯通四件事：

| 项 | 内容 | 验收 |
|---|---|---|
| 运行身份 | `ops.data_run_attempt` + `run_record.json` + git SHA | 同一天跑两次，两条 attempt 都在，manifest 指向最后一次 |
| 确定性通知 | 由结构化产物生成，记录 `ops.notification_delivery` | 消息里有股票、来源、`run_id`、链接；投递失败能查到并触发告警 |
| 个股线索 | `lead_timeline` 以 `review_item_snapshot` 为第一个来源；提供 `/api/assets/{id}/leads`；观察池写入 | 第 3 节的验收标准 |
| 可信标识 | `provenance` 各维度；策略实验室 fixture 显著标示；个股 URL | 投资研究页面不会把 fixture 或回退数据显示成正式结果 |

不在第一阶段：存储治理、全部 reader 迁移、asset_master 合并、导航重组、多市场字段落库（只先统一解析函数）。

## 7. 对 PR #19 原报告的更正索引

| 原文 | 更正 |
|---|---|
| RUNTIME §3 R1：在 metadata 中加 `attempt_id` | 由本文 §1 取代：新增只追加的 attempt 表 |
| RUNTIME §3 R5：写一行 `delivered` 状态 | 由本文 §2 取代：单独的通知投递表，分阶段记录 |
| RUNTIME §4 方案 C：4 个来源 | 由本文 §3 补充：第一个来源是 `review_item_snapshot`，已覆盖真实策略候选 |
| DATA §4：Mid Trend 当天可用 | 由本文 §4 补充：不在 EOD 路径，影响研究归因 |
| DECISION §5：currency 默认 CNY | 由本文 §5 更正：未知写 `UNKNOWN` |
| UIUX §5：单一 `status` | 由本文 §5 更正：拆成多个维度 |
