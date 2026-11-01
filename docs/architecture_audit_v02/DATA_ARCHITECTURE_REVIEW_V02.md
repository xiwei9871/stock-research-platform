# 数据架构评审 V0.2

基线 `9bd95562`。数据库数字来自 2026-11-01 的只读统计（只读事务，只查系统视图和元数据），以下记为 RUNTIME_VERIFIED。数字已取整，不含主机信息。

## 1. Schema 体量与数据角色

| schema | 体量（约） | 角色 | 可否重建 |
|---|---|---|---|
| factor | 271 GB | 计算结果：`factor_daily` 228 GB、`stock_score_daily` 8 GB、`stock_technical_features_daily` 29 GB | **可重建**（从 market 层），但代价高 |
| market | 264 GB | 事实：分钟线（其中 default 分区 135 GB 为 2020–2023 年）、竞价、公司行为、指数、交易日历 | 外部数据源可重抓，但很慢；baostock 有黑名单风险 |
| public | 81 GB | 历史兼容：`market_daily_bar` 22 GB（**日线的规范表**）、`label_snapshot` 45 GB、`feature_snapshot`、旧版 `asset_master` | 日线是事实；label/feature 快照可重建 |
| raw_baostock / raw_akshare | 25 GB / 2.5 GB | 原始 payload，只追加，作为供应商版本证据 | 不可替代（历史观测） |
| backup | 15 GB（151 个关系） | R2 修订工作区（`DOCUMENT_ONLY`：仍在使用） | 需逐项判断 |
| staging | 11 GB | 采集落地的中间表 | 落库后可清理（需先验证键匹配率） |
| p1d1/p1d3_shadow、m1_shadow、p1d3_test | 约 6 GB | DATA-R3 的 shadow 演练数据 | 演练结束后可归档 |
| core | 3.4 GB | 证券主数据、`asset_status_daily`、生命周期事件 | 事实 |
| finance / fundamental | 0.7 GB | 财报三表、指标 | 事实（以 raw payload 为证据） |
| research | 0.9 GB | 研究 case、claim、证据、主题研究 | **不可丢失的人工研究状态** |
| watchlist | 很小 | 观察池 | **人工状态，不可丢失** |
| ops | 25 MB（42 个关系） | 运行台账和 operator 决策 | 运行台账可补录；**operator 决策和复核属于人工状态** |

关键点：**体量最大的是可重建的计算结果，而最小、最不能丢的是人工研究状态。** 备份和生命周期策略应该按这个区分来设计，不能按体量设计。DESIGN

## 2. `factor.factor_daily` 存储方案比较

现状（SOURCE_VERIFIED + RUNTIME_VERIFIED）：
- 窄长表，主键是 `(trade_date, asset_id, factor_name, calc_version)`，每行只存一个因子值，并带 `factor_group`、`source`、`source_data_version`、`computed_at` 等文本列（`schema.py:1920-1931`）。
- 约 6.1 亿行。总大小 228 GB，其中索引约 158 GB（pkey 44 GB、asset_history 54 GB、eval_lookup 55 GB、lookup 4.8 GB）。
- 不是分区表。
- 10-28 恢复实例上的数据（DOCUMENT_ONLY）：同样定义的索引新建后约 112 GB；W2（单资产时序）冷查询 186 秒，W3（回测批量读取）冷查询 377 秒，瓶颈在堆表的随机读取。

| 方案 | 查询性能 | 写入/更新 | 版本管理 | PIT 复现 | 磁盘 | 迁移风险 | 代码兼容 | 维护 |
|---|---|---|---|---|---|---|---|---|
| 1. 长表 + 索引/访问模式优化（REINDEX，删掉被覆盖的索引，查询改成先按日期范围过滤） | 有限改善；REINDEX 可回收膨胀（估计上限约 46 GB）；堆表随机读取不变 | 不变 | 现有 `calc_version` | 不变 | 小幅下降；每次 REINDEX 需要约 65 GB 临时空间 | 低到中（需要空间余量） | 完全兼容 | 低 |
| 2. 长表按 `trade_date`（按年）分区，冷分区可以 DETACH | 带日期条件的查询可以裁剪分区；单资产全历史查询需要扫所有分区 | 每日写入只落在当年分区 | 同上 | 冷分区可以冻结成不可变快照 | 冷分区可以 DETACH 后导出并删除，空间**真正释放** | 中：需要重建整表，迁移期需要双倍空间 | 对 SQL 透明 | 中（要维护分区） |
| 3. 保留长表，按研究负载生成宽表投影（例如某个因子组的"资产×日期"矩阵，物化视图或独立表） | 对固定负载可能大幅改善（NOT_VERIFIED） | 每天要刷新投影 | 投影要记录来源版本 | 投影要有快照 id | **增加**存储 | 低（新增，不改原表） | 只有新消费者用投影 | 中（两份数据要保持一致） |
| 4. Parquet + DuckDB 离线分析 | 扫描型负载有优势；点查不如 PG | 不适合日常增量写入；只适合冻结的历史数据 | 目录或文件哈希即版本 | 文件不可变，天然可复现 | 前提是导出后 PG 端删除，否则是**复制** | 中 | 需要另写一套读取路径 | 中 |

判断（DESIGN，必须经负载测试确认）：
- 没有真实负载数据之前，不能声称任何方案能带来数量级的提升。
- 磁盘压力主要来自"同一组键存了 3 份完整索引"和"大量可重建数据长期在线"，不是 PG 本身不合适。
- 方案 1 的 REINDEX 只是一次性回收，不改变数据随时间增长的速度。
- 方案 2 是唯一既兼容现有代码、又能让冷数据真正离开 PG 的路径，但迁移期间需要双倍空间。
- 方案 3 和 4 解决的是查询速度，不解决磁盘问题；方案 4 在 PG 端删除冷数据后才能节省空间。
- 推荐的验证顺序：先在 185 恢复实例上，用 W2/W3 加上一个真实的回测读取，分别测方案 1（REINDEX 加查询改写）和方案 2（按年分区）。只有这两种都不够时，再测方案 3。方案 4 只用于分钟线这类已冻结的历史数据。

## 3. 数据生命周期

| 类别 | 例子 | 建议位置 | 恢复方式 |
|---|---|---|---|
| 事实，必须在线 | 日线、`asset_status_daily`、交易日历、财报、最近 2 年分钟线 | PG | L2 备份；将来上 PITR |
| 事实，冷数据 | 2020–2023 年分钟线 | Parquet（NAS 上保留两份）。PG 端在验证后 DETACH 加 DROP | Parquet 和 L2 备份 |
| 原始证据 | raw payload | PG，只追加 | L2 备份 |
| 可重建的计算结果 | `factor_daily`、label/feature 快照、技术特征 | PG（热数据）；冷数据只保留重建脚本和版本 | 重算；L2 备份 |
| 人工研究状态 | research.*、watchlist.*、operator 决策和复核 | PG | **单独做高频小备份**（这部分只有 MB 级，可以每天备份） |
| 运行台账 | ops 中的运行表 | PG | 可以从本地运行文件补录 |
| 生产硬依赖文件 | gitignored 的 `outputs/research/...` CSV | 本地，加 NAS 镜像 | 目前只有 `AGENTS.md` 里的一段文字说明，**没有登记，也没有校验和** |

DESIGN：备份分两层。人工状态加主数据每天做一次小 dump（MB 级）；全库 L2 每周一次，**必须写到数据库盘以外的位置**。11-01 的事故是因为本地每周全库备份写满了数据库所在的磁盘（USER_STATED，宿主机日志我没看到）。

## 4. PIT 与读取契约

| 规则 | 位置 | 语义 | 状态 |
|---|---|---|---|
| 交易资格 | `tradeability.tradeability_at` / `compute_pit_limit_flags` | 按交易所、板块、ST、新股窗口、生效日期选择规则；规则未知时 fail-closed | 统一但很少被调用（4 个模块） |
| 财务信号 PIT | `financial_pit.financial_pit_at` | 日级公告日按 D+1 才可用；哨兵值 fail-closed | **没有消费者**；Mid Trend 用的是 `announcement_date > trade_date`（当天即可用） |
| 研究截止 PIT | CAP-01 `_pit_status`、CAP-02 `_pit_ok` | 日期 ≤ 研究截止日；`ingested_at` 作为约束 | 领域内统一 |
| 回测执行时点 | PR #16 `signal_schedule` / `signal_ts` | 带时区、可配置截止时点 | 未合并 |

结论：
- 这四套规则属于**领域差异**，不应该合并成一个函数。
- 真正的冲突是同一种用途用了不同规则：财务信号这一类，`financial_pit` 和 Mid Trend 的写法不一致；涨跌停这一类，`tradeability` 和 `core_data` 的固定阈值不一致。
- 最小修正（DESIGN）：每一类用途只保留一个读取函数，消费者逐步迁移过去，不要求每张表都加时间字段。

## 5. DuckDB 的适用条件

DESIGN，有条件：
- 单人使用、夜间批量写入、Dashboard 点查，这些都不需要 DuckDB。
- DuckDB 的 postgres 扩展可以直接 `ATTACH` 正在运行的 PG 来读表，不需要持久化第二份数据。但扫描速度受 PG 和网络限制。
- 只有一种情况适合引入：分钟线或因子的冻结历史已经导出成 Parquet，并且 PG 端已经删除，此时 DuckDB 作为读取这些文件的执行器。
- 在 PR #16 Gate C 和 §2 负载测试完成之前，不引入。

## 6. 多市场数据契约

详细内容见 `ARCHITECTURE_DECISION_PROPOSAL_V02.md` §5。数据层要点：
- `core.asset_master` 被 48 个文件引用，是事实上的主表。但它有 `is_star`、`is_chinext`、`is_beijing` 这类 A 股布尔列，3 个供应商代码列，却**没有 currency**。
- `public.asset_master` 有 market 和 currency，被 7 个文件引用。两表之间只有 public → core 的单向同步，而 `market_profile_backfill.py:154` 只更新 core 表，两表可能出现漂移。
- `market.trading_calendar` 的 exchange 列用的是 `SSE`（`dashboard/bars.py:208`），而资产表的 exchange 用 `SH`，两套代码词汇不一致。
- `finance.*` 表的字段名是中性英文，但没有 currency、reporting_standard、fiscal_year_end；`report_type` 默认财年结束日是 12-31。
- 暂时不建议合并两张 asset_master，迁移风险需要先评估。现在应先把读取统一到一个解析函数和一个读取函数上。
