# Strategy DB-Only Preflight and Runtime Contract

## Context

研究策略必须使用研究数据库中的已落库数据。策略运行过程中不能为了补齐数据而调用 BaoStock、Tushare、AkShare 或其他外部数据源；缺失数据必须转成独立的回填任务，由回填流程异步处理。当前消费超跌策略已经能够在约 145 秒内完成一次完整生成，因此本次重点是把这条快路径固化为可验证的运行契约，并让缺数、耗时和数据来源都可审计。

## Goals

1. 为策略提供统一的 `db_only` 数据策略，默认拒绝策略链路中的外部抓取。
2. 在消费超跌策略进入评分前完成数据库覆盖预检；发现硬缺口时阻断选股，只生成回填任务清单和阻断诊断。
3. 在产物中记录数据来源策略、预检结果、各阶段耗时和总耗时。
4. 为策略设置 60 分钟运行预算；在阶段边界检查超时并以明确状态退出。
5. 保持现有 V1/V2 排名、PIT 截止日期和原有正常产物格式不变。

## Non-goals

- 本次不改 BaoStock 回填 worker 的吞吐实现；回填性能单独开任务。
- 本次不把 5 分钟线强行加入候选生成所需数据；5 分钟线仍属于结果验证/诊断数据。
- 本次不把所有历史策略一次性重构；先建立共享契约并接入消费超跌，后续策略按同一接口迁移。

## Design

### 1. Shared policy

新增 `stock_research.strategy_data_policy`，提供：

- `DB_ONLY` 常量和策略运行时校验；
- 标准化的数据缺口记录（数据集、资产、日期范围、实际/期望行数、原因）；
- 将缺口写成确定性 JSON 回填请求的函数；
- `StrategyRuntimeBudget`，记录阶段耗时并在阶段边界执行 60 分钟截止检查。

该模块不导入任何外部数据客户端。策略只接收数据库 loader 返回的 DataFrame 或已存在的本地证据文件。

### 2. Consumer preflight

消费超跌 runner 按以下顺序工作：

1. 读取本地证据和静态规则；
2. 通过现有 DB loader 读取 universe、股本、日线、财务和估值历史；
3. 构造 PIT consumer universe，得到真正参与策略的资产集合；
4. 对参与资产检查：日线历史字段/截止日、股本字段、至少一条 PIT 财务记录、至少一条 PIT 估值记录；历史长度按策略所需的 504 个交易日检查，上市不足该长度的资产按可用上市历史计算，不因新股自然短历史而误报；
5. 无缺口时进入现有评分与发布；有缺口时不调用评分、不发布 Top20/Top30/Reserve，只写阻断诊断和回填请求。

缺口请求包含 strategy、trade_date、ranking_version、data_source_policy、生成时间、缺口列表以及建议的回填 dataset。回填请求是计划，不是回填执行。

### 3. Artifacts and status

正常发布的 coverage JSON 增加：

- `data_source_policy: "db_only"`
- `preflight_status: "passed"`
- `runtime_seconds`
- `stage_timings_seconds`
- `runtime_budget_seconds: 3600`

缺数时输出目录只包含：

- `consumer_oversold_data_gap_coverage.json`
- `consumer_oversold_backfill_request.json`
- `consumer_oversold_data_gap_report.md`

并返回/打印 `blocked_missing_data`。此状态不伪造正常的排名产物，也不覆盖上一次 `current` 正常发布。

### 4. Runtime and performance

阶段计时覆盖 universe、share capacity、market history、turnover derivation、finance、valuation、preflight 和 scoring/publishing。每个阶段结束检查预算；超时返回 `runtime_timeout`，同样不发布排名。当前 145 秒基线远低于 3600 秒，后续可根据阶段计时对特征计算做向量化或缓存，且不改变结果。

## Error handling

- 数据库连接或查询失败：抛出原有错误，不回退到外部数据源。
- 缺少数据但请求可补齐：生成 `backfill_required` 缺口，不执行回填。
- 缺少静态规则/证据文件：保持现有文件错误行为。
- 超过运行预算：生成 `runtime_timeout` 诊断，不发布排名。
- 任何外部抓取尝试：由 `db_only` 策略边界拒绝并记录错误。

## Testing and acceptance

测试先行覆盖：

1. 完整数据库帧通过预检，正常排名结果与基线一致；
2. 缺日线/财务/估值/股本时预检失败，生成回填请求且不产生排名文件；
3. 运行结果包含来源策略、预检状态、阶段耗时和预算；
4. 运行器不会调用外部数据客户端；
5. CLI 能正确报告 `blocked_missing_data` 和缺口产物；
6. 现有 consumer V1/V2 测试和全量回归不受影响。

