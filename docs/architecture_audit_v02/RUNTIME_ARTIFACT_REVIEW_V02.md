# 运行台账、研究产物与通知链路评审 V0.2

基线 `9bd95562`。运行记录来自本地日志、调度器本地状态库（只读）和生产库只读查询。本文已脱敏，不含主机信息、通知目标和凭证。

## 1. 已有运行能力清点

| 机制 | 位置 | 覆盖范围 | 状态 |
|---|---|---|---|
| `ops.daily_pipeline_job / quality / failed_symbol / status` | `daily_close_pipeline.py:62-135` | daily-close：采集、质量检查、失败标的；`daily_pipeline_status` 给出 READY / DEGRADED_READY / NOT_READY | PROD，SOURCE_VERIFIED |
| `ops.data_run_manifest` | `data_run_manifest.py:20` | EOD 发布阶段的各模块，以及 `eod_auto_repair` 的补录。10-29 共 17 行 | PROD，RUNTIME_VERIFIED |
| `ops.strategy_daily_eod_status` | `strategy_daily_eod_store.py:12` | 每个交易日一行，每个策略一列 | PROD，RUNTIME_VERIFIED |
| `commit_strategy_publication()` | `strategy_daily_eod.py:482` | manifest 和 status 在同一事务内写入，并检查必需模块都为 success | PROD，SOURCE_VERIFIED |
| EOD 发布锁 | `strategy_daily_eod.py:75,178`（`fcntl.flock` 非阻塞，等待后超时报错） | 单机互斥 | PROD，SOURCE_VERIFIED |
| EOD 依赖探针 | `run_strategy_daily_eod_cron.sh` 的 `wait_for_daily_pipeline_status`，最长等 240 分钟 | 通过 `daily_pipeline_status` 衔接 daily-close 和 EOD | PROD，RUNTIME_VERIFIED（10-29 等待了 2400 秒） |
| `eod_auto_repair` | `eod_auto_repair.py` | 读取 `strategy_eod_publish_summary.json` **文件**来判断是否需要修复，再写 manifest | PROD，SOURCE_VERIFIED |
| `ops.daily_job_run` | `daily_job_run_store.py` | 只被 `daily_health.py` 读取 | 孤立，SOURCE_VERIFIED |
| `ops.intraday_job` | `intraday_pipeline.py` | 只有写入方自己读取 | 孤立 |
| `ops.research_queue_refresh_run` | `research_queue_refresh_store.py` | 只有写入方自己读取 | 孤立 |
| `ops.operator_*_run`（11 个） | `operator_*` 模块 | shadow 实验与复核 | 各自独立 |
| 交易日守卫 | `stock_cron_guard` | 非交易日跳过 | PROD |
| 调度 | OpenClaw 7 个启用作业（agentTurn，由 LLM 执行脚本并汇总 stdout）；crontab 8 条竞价采集；launchd 5 个 agent | — | RUNTIME_VERIFIED |

**更正**：运行台账已经存在，而且 EOD 发布这一段做得相当完整（同一事务提交、加锁、依赖探针）。

## 2. 为什么有运行管理代码，诊断和恢复仍然困难

1. **至少 6 个运行状态家族，没有共享键。** daily-close 用 `(trade_date, job_name, stage, source)`；EOD 用 `run_id = strategy-eod-{date}-local`；repair 用 `eod-auto-repair-reports-{date}`；其余各自定义。只有 `trade_date` 可以把它们串起来，但同一天的多次重跑无法区分。SOURCE_VERIFIED
2. **`run_id` 由日期决定，不是唯一运行标识。** `strategy_eod_publish.py:163` 写死 `f"strategy-eod-{selected_trade_date}-local"`。同一天重跑会覆盖之前的记录，失败和成功两次尝试无法同时保留。SOURCE_VERIFIED
3. **`code_version` 不是 git SHA。** 10-29 的 17 行中，只有 3 个策略模块填了版本字符串（例如 `tech_bottleneck_v1`），其余为空。`strategy_eod_publish.py:811` 实际写入的是 `source_kind`。RUNTIME_VERIFIED
4. **上游数据模块只在 EOD 里登记一行摘要。** `daily_bars`、`score_topn`、`technical_features` 在 manifest 中有行数但没有 `artifact_path`，也没有关联到 `daily_pipeline_job` 的具体记录。RUNTIME_VERIFIED
5. **失败类型没有分开。** `strategy_daily_eod_status` 只有每个策略一个状态字段，加一个 `error_summary` 文本。依赖失败、环境失败（10-30 的 tabulate）、计算失败、发布失败都写成 `failed`。SOURCE_VERIFIED / RUNTIME_VERIFIED
6. **运行状态只记在数据库里。** 11-01 01:08 那次重跑跑了 1 小时 40 分钟，失败点恰好是写 `strategy_daily_eod_status`，原因是数据库处于恢复模式。数据库一旦不可用，连"本次失败"都记不下来。repair 读的是文件，EOD 写的是数据库，两边的真实状态来源不一致。RUNTIME_VERIFIED
7. **调度层看不到业务状态。** OpenClaw 的作业状态取决于脚本退出码和 stdout，它自己的 run 记录有 `run_id` 列但没有填写，也不知道 manifest 里的 `run_id`。

## 3. 最小改造方案（DESIGN，不新建平行系统）

把 `ops.data_run_manifest` 作为公共查询入口，只做增量补充：

| 改动 | 内容 | 代价 |
|---|---|---|
| R1 每次尝试一个唯一 `attempt_id` | 保留现有 `run_id`（按日期的业务键），在 `metadata` jsonb 中加 `attempt_id`（UUID）、`trigger`（cron / repair / manual）、`git_sha` | 不改表结构 |
| R2 失败分类 | 在 `metadata.failure_class` 中记录 `dependency / environment / compute / publish / notify`；`status` 沿用现有枚举 | 不改表结构 |
| R3 本地兜底记录 | 每次运行在运行目录写 `run_record.json`（与 manifest 同结构）；数据库不可用时只写文件，恢复后由 repair 补录 | 新增约 50 行 |
| R4 上游接入 | daily-close 结束时为每个 stage 写一行 manifest（tier1，`artifact_path` 指向 `daily_pipeline_job` 的键），不改动 daily-close 自己的表 | 少量代码 |
| R5 通知回写 | 通知发出后写一行 `module=notify_<channel>`，`run_id` 与 EOD 相同，状态记为 delivered / failed | 少量代码；需要能拿到调度器的投递结果 |

不做的事：不新建 ResearchRun 表；不合并 operator 系列表；不更换调度器。

## 4. Research Lead（研究线索）

需要回答的问题是：以某只股票为中心，查出它被谁发现、什么时候、用了哪些数据、原因是什么、产物在哪里、之后有什么变化、用户是否看过。

现有的承载对象（SOURCE_VERIFIED）：各策略每日的 review CSV、`review_queue_strategy_manifest.csv`（15 行，带 `strategy_run_id`）、`ops.review_item_snapshot`、`watchlist.watchlist_item`（有两个写入方）、`ops.operator_decision_event`、`research.review_action`、`research.tech_bottleneck_review_decision`、CAP envelope（只能按主题查）、通知记录（不带键）。

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A. 统一持久化表 | 所有模块直接写入 `research.lead` | 查询最简单 | 需要改所有写入方，耦合最高；历史数据要回填 |
| B. 事件日志加当前状态读模型 | 各模块发出 `lead_event`（asset_id、source、kind、run_id、artifact_ref、occurred_at），由一个投影维护当前状态 | 可回放，可解释变化 | 需要事件契约和投影维护；对单人项目偏重 |
| C. 关联现有表，加聚合查询 | 一个只读函数或视图 `lead_timeline(asset_id)`，对现有来源做 UNION（manifest 指向的 review CSV 加 snapshot、watchlist、decision、review_action），输出统一的行结构 | 不改写入方，可以逐个来源接入，风险最低 | 依赖各来源已有的 `asset_id` 和日期；CSV 来源需要先入库或建索引 |

**推荐 C，演进方向是 B**（DESIGN）：
1. 先实现 `lead_timeline(asset_id, since)` 读取函数，加一个只读 API，接入 4 个已经入库的来源：`ops.review_item_snapshot`、`watchlist.watchlist_item`、`ops.operator_decision_event`、`research.review_action`。
2. 每条记录带 `source_module`、`run_id`、`occurred_at`、`reason`、`artifact_ref`。
3. 对没有入库的 CSV 来源，用 manifest 的 `artifact_path` 指过去，不复制内容。
4. 只有当聚合查询的维护成本明显上升时，才考虑换成 B 的事件日志。

## 5. 全链路审计：2026-10-29 的一条 Tech Bottleneck 结果

样本：`tech_bottleneck` 当日排名第 1 的候选（深市创业板一只股票，股票代码只记录在内部证据中）。

```mermaid
flowchart TD
  A[日线 / 状态 / 因子<br/>max(trade_date)=10-30 ✔] --> B[daily_close → ops.daily_pipeline_status READY]
  B -->|依赖探针等待 2400s ✔| C[strategy_daily_eod]
  CSV[[153 只固定名单 CSV<br/>gitignored · 无校验和 ⚠]] --> C
  C --> D[[strategy_tech_bottleneck_review.csv 第 1 行 ✔]]
  C --> E[[review_queue_strategy_manifest.csv 15 行 ✔]]
  C -->|同一事务| F[(ops.data_run_manifest 17 行<br/>run_id=strategy-eod-2026-10-29-local ✔<br/>code_version=tech_bottleneck_v1 ✘ 非 SHA)]
  F --> G[(ops.strategy_daily_eod_status success ✔)]
  D -->|rsync 同步 · 未验证 ?| H[展示主机产物目录]
  H --> I[/api/review-queue 读 manifest → artifact_path ✔ 代码]
  I --> J[ReviewQueueWorkspace 显示 run_id ✔ 代码]
  J -->|onOpenStock 只改 React 状态 · 不改 URL ⚠| K[StockWorkspace：不显示 Tech Bottleneck 来源 ✘]
  C -->|stdout| L[OpenClaw LLM 摘要 → 飞书 delivered ✔<br/>不带 run_id、不带股票 ✘]
```

| 步骤 | 状态 | 证据 |
|---|---|---|
| 数据来源完整 | 已验证 | 10-27 至 10-30 每天 5188–5189 行 |
| 计算 | 已验证 | review CSV 第 1 行，`strategy_run_id` 与 manifest 一致 |
| manifest | 已验证 | 17 行，`artifact_path` 指向 review CSV |
| 运行输入可追溯 | **断点** | 153 只名单 CSV 没有登记，manifest 也不记录它的校验和 |
| 代码版本 | **断点** | 记录的是版本字符串，不是 SHA |
| 同步到展示主机 | 尚未验证 | 本轮没有访问展示主机 |
| API | 代码推断 | `review_queue.py:293,321` 按 manifest 的 `artifact_path` 读取 |
| React 页面 | 代码推断 | ReviewQueueWorkspace 显示 run_id；个股页拿不到这条来源 |
| 通知 | 已验证（已送达） | 调度器本地记录显示 10-29 23:00 delivered；摘要是 LLM 生成的文字，只有状态和条目数，**没有股票和 run_id** |
| 用户是否看到或复核 | **无法判断** | 没有"已看"状态；复核动作要等用户主动操作 |

附带发现（RUNTIME_VERIFIED）：
- **10-28 EOD 成功，但通知未送达**（调度器 `noOutputTimeoutSeconds`）。10-27 也一样。这是"计算成功不等于已通知"的真实案例。
- 同一个 `review_queue_strategy_manifest.csv` 中，LHB 的 5 行 `asset_id` 用的是 ts_code 格式，另外两个策略用的是 `CN:` 格式。API 层用 `normalize_cn_equity_asset_id` 做了统一（`review_queue.py:1190`）。

## 6. 断点排序

1. 通知与运行没有键关联，送达失败不进业务状态（10-27、10-28 已经发生过）。
2. 个股页拿不到"谁标记了这只股票"。
3. 运行输入文件没有登记，也没有校验和。
4. `run_id` 不是每次尝试唯一，`code_version` 不是 SHA。
5. 数据库不可用时没有本地运行记录。
