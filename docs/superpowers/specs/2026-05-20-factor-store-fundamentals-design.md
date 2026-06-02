# Factor Store Fundamentals Integration Design

## 1. Goal

为现有 `factor.factor_daily` 主日频因子流补齐一条最小可用的基本面接线闭环：

- 使用 point-in-time safe 财报读取
- 将 `quality + value` 因子接入 `build_and_store_factor_daily()`
- 让新因子进入 registry 与 `candidate_factor_names()`
- 保持 `manual_v1` 当前评分权重不变

第一版目标不是重做整套因子框架，也不是立刻改变现有评分结果，而是让基本面因子首次进入统一主因子写入链路，并且不绕过 metadata / registry 约束。

## 2. Scope

### In Scope

- 把第一批 `quality + value` 因子接入 `factor_pipeline.py`
- 复用 point-in-time finance service 组装 fundamentals snapshot
- 将 fundamentals rows 统一转换为 `factor.factor_daily` 长表格式
- 为新因子补 registry metadata
- 让新因子进入 `candidate_factor_names()`
- 为主写入链路补 registry / shape 约束测试

### Out of Scope

- 不接 `growth` 因子
- 不改数据库 schema
- 不改 `manual_v1_config()["weights"]`
- 不让新因子立即影响当前总分结果
- 不新增缺失值填充、横截面插补或 winsorization
- 不重构 `factor_store.py` 成新的持久化层

## 3. Current State

当前仓库具备三块已有能力，但尚未闭环：

### 3.1 Registry 已存在，但只覆盖现有技术/行业类因子

`factor_registry.py` 已经提供：

- `FactorMetadata`
- `list_factor_names()`
- `factor_groups_map()`
- `factor_directions_map()`
- `factor_availability_metadata()`
- mapping 校验函数

但 registry 里还没有第一批基本面因子 metadata。

### 3.2 PIT-safe finance service 已存在

`services/point_in_time_finance.py` 已经支持：

- `get_latest_indicator()`
- `get_latest_income_statement()`
- `get_latest_balance_sheet()`
- `get_latest_cash_flow()`

这些函数通过 `announcement_date <= trade_date` 做 point-in-time safe 读取，已经满足第一版 fundamentals 接线的时间安全要求。

### 3.3 基本面因子计算函数已存在，但尚未进入主流水线

已有：

- `factors/quality.py`
- `factors/value.py`

但当前 `build_and_store_factor_daily()` 主线仍主要服务于 technical / sector / external alpha，基本面因子尚未完整接入主日频因子流。

## 4. Design Principles

- 主入口不变：继续使用 `build_and_store_factor_daily()` 作为主日频写入入口
- PIT-first：所有 fundamentals 读取必须复用现有 point-in-time service
- registry-first：新因子先进入 registry，再允许进入主写入链路
- score-stable：第一版允许新因子写入 `factor.factor_daily` 并进入候选集，但不修改当前 `manual_v1` 权重
- 缺失不阻断：个股财报缺失时只跳过对应 fundamentals rows，不阻断整日技术因子构建

## 5. Target Factor Set

第一版只接以下因子：

### Quality

- `roe`
- `roa`
- `gross_margin`
- `net_margin`
- `debt_ratio`
- `ocf_to_np`

### Value

- `pe_ttm`
- `ps_ttm`
- `pb`

这 9 个因子足以形成一条最小 fundamentals 主线，同时不把范围扩到 `growth`。

## 6. Proposed Architecture

### 6.1 Main flow

`build_and_store_factor_daily()` 的执行结构调整为：

1. 加载现有市场 bars / 行业数据
2. 生成现有 technical / sector / external alpha rows
3. 加载 fundamentals snapshot
4. 生成 `quality + value` factor rows
5. 合并所有 factor rows
6. 在写入前统一做 registry / shape 校验
7. 调用 `upsert_factor_daily()`

### 6.2 New fundamentals snapshot adapter

在 `factor_pipeline.py` 中新增一层 fundamentals adapter，职责是：

- 对给定 `trade_date` 收集当日股票列表
- 逐个股票调用 PIT finance service
- 组装一张当日 fundamentals snapshot frame
- 输出给 `compute_quality_factors()` / `compute_value_factors()`

该 adapter 是第一版中唯一的新“基本面适配层”。不新增新的持久化表，也不改现有 service API。

## 7. Data Flow Details

### 7.1 Universe of assets

fundamentals snapshot 使用当日已有市场 bars 的 `asset_id` 作为股票集合来源，而不是额外查询一套资产池。

原因：

- 与现有因子流对齐
- 避免让 fundamentals 写入范围与 technical 写入范围分叉
- 减少第一版引入的资产选择复杂度

### 7.2 PIT record selection

对每个 `asset_id`、`trade_date`：

- indicator：来自 `get_latest_indicator()`
- income：来自 `get_latest_income_statement()`
- balance：来自 `get_latest_balance_sheet()`
- cash flow：来自 `get_latest_cash_flow()`

所有记录都必须满足：

- `announcement_date <= trade_date`

第一版不额外做财报口径优选逻辑，直接复用现有 service 的“最新可见记录”定义。

### 7.3 Snapshot schema

fundamentals snapshot 至少需要包含：

- `asset_id`
- `close`
- `total_share`
- `float_share`
- `roe`
- `roa`
- `gross_margin`
- `net_margin`
- `debt_ratio`
- `ocf_to_np`
- `np_parent_ttm`
- `revenue_ttm`
- `equity_parent`

其中：

- `close` 来自当日市场 bars
- `total_share` / `float_share` / `np_parent_ttm` / `revenue_ttm` / `equity_parent` / `roe` / `roa` / `gross_margin` / `net_margin` / `debt_ratio` / `ocf_to_np` 来自 PIT finance rows 适配

第一版允许部分快照字段缺失，只要计算函数能自然产出 `NaN` 并在后续长表转换时被过滤。

## 8. Factor Row Construction

### 8.1 Quality rows

`compute_quality_factors(snapshot)` 输出横表后，转换为长表：

- `trade_date`
- `asset_id`
- `factor_name`
- `factor_group = "quality"`
- `factor_value`
- `calc_version = "v1"`
- `source = "fundamental"`
- `source_data_version = "pit_finance_v1"`

### 8.2 Value rows

`compute_value_factors(prices, finance, shares)` 在第一版中可由统一 snapshot 派生：

- `prices` 使用 `asset_id + close`
- `finance` 使用 `asset_id + np_parent_ttm + revenue_ttm + equity_parent`
- `shares` 使用 `asset_id + total_share + float_share`

输出后同样转换为 `factor.factor_daily` 长表，`factor_group = "value"`。

### 8.3 Missing handling

转换长表时：

- `factor_value` 为 `NaN` 的行直接丢弃
- 对同一股票允许只写入部分 fundamentals 因子
- 不因单只股票 fundamentals 不完整而阻断整日运行

## 9. Registry Changes

`factor_registry.py` 需要新增 9 条 metadata：

- `roe`
- `roa`
- `gross_margin`
- `net_margin`
- `debt_ratio`
- `ocf_to_np`
- `pe_ttm`
- `ps_ttm`
- `pb`

每个因子至少需要：

- `factor_name`
- `factor_group`
- `direction`
- `description`
- `source`

推荐方向：

- `roe` / `roa` / `gross_margin` / `net_margin` / `ocf_to_np`：`higher`
- `debt_ratio`：`lower`
- `pe_ttm` / `ps_ttm` / `pb`：`lower`

`source` 统一使用：

- `fundamental`

## 10. Candidate And Score Behavior

### 10.1 Candidate list

新因子进入 registry 后，`candidate_factor_names()` 将自动包含这些因子。

这是第一版的明确目标之一：让 fundamentals 因子成为系统认可的合法候选因子。

### 10.2 Score behavior

`manual_v1_config()["weights"]` 第一版不改。

因此：

- fundamentals 因子会写入 `factor.factor_daily`
- fundamentals 因子会出现在 `candidate_factor_names()`
- 但它们不会自动进入当前 `manual_v1` 总分，因为没有对应 score weight

这样可以保证：

- 主评分结果保持稳定
- fundamentals 主线先接通
- 后续单独做“是否进入打分”的策略变更

## 11. Validation And Write Constraints

第一版写入前需要保证：

- 所有 `factor_name` 都能在 registry 中找到
- `factor_group` 必须与 registry 一致
- 新 fundamentals rows 必须满足 `FACTOR_DAILY_COLUMNS`
- 未注册因子一律报错

第一版不要求：

- 对 `source_data_version` 做复杂 lineage 层次拆分

但需要至少固定 fundamentals 的 lineage 文本，例如：

- `pit_finance_v1`

## 12. File-Level Changes

### Modify: `src/stock_research/factor_pipeline.py`

新增：

- fundamentals snapshot loader
- quality rows builder
- value rows builder
- 主 `build_and_store_factor_daily()` fundamentals 拼接逻辑

### Modify: `src/stock_research/factor_registry.py`

新增 9 条 fundamentals factor metadata。

### Optional Modify: `src/stock_research/factor_store.py`

仅当现有写入前约束不足以保护 registry / shape 时，再做最小增强。若 `factor_pipeline.py` 已能在写入前完成校验，则不强行扩逻辑。

### Reuse unchanged if possible

- `src/stock_research/factors/quality.py`
- `src/stock_research/factors/value.py`
- `src/stock_research/services/point_in_time_finance.py`

## 13. Testing Strategy

需要覆盖以下几类测试：

### Unit tests for fundamentals snapshot / pipeline integration

- PIT snapshot 只读取 `announcement_date <= trade_date`
- 当 finance rows 缺失时，technical/sector 构建仍继续
- `quality + value` 输出正确转换为 long factor rows

### Registry tests

- 新 fundamentals 因子出现在 `candidate_factor_names()`
- group / direction / metadata 映射正确

### Score stability tests

- `manual_v1_config()["weights"]` 未变化
- 新因子写入后，不会自动影响当前 `manual_v1` 总分列选择逻辑

### Store-shape tests

- 新 fundamentals rows 满足 `FACTOR_DAILY_COLUMNS`
- 未注册 fundamentals 因子仍会报错

第一版继续采用 monkeypatch / fake rows 单测，不访问真实数据库。

## 14. Risks And Mitigations

### Risk: 财报字段口径不一致

现有 quality/value 计算函数较轻，依赖 snapshot 字段命名准确。如果 adapter 映射不清楚，容易出现“代码能跑但因子全空”。

Mitigation:

- 在 snapshot adapter 中显式列出字段映射
- 用单测锁定最小有效输入和预期输出

### Risk: fundamentals 缺失拖垮整日因子构建

若把财报缺失当 hard failure，会使主因子流对财报覆盖过度敏感。

Mitigation:

- 缺失只影响对应 fundamentals rows
- 不影响 technical / sector rows 的写入

### Risk: candidate list 扩大后误以为已进入当前评分

用户可能误解“进入 candidate list”就等于“进入 manual_v1 score”。

Mitigation:

- spec 明确区分 candidate registration 和 active weighting
- 测试锁定 `manual_v1` 权重不变

## 15. Completion Criteria

第一版完成的标志：

- `quality + value` 因子可以通过 `build_and_store_factor_daily()` 写入 `factor.factor_daily`
- 新因子已经进入 registry 和 `candidate_factor_names()`
- 现有 `manual_v1` 评分结果不被改变
- 缺失 fundamentals 不会阻断整日因子构建
- 相关测试通过

第一版不以“基本面因子已进入实盘评分”为完成标志，而只以“主因子写入链路已接通”为完成标志。

## 16. Recommendation

按本设计推进时，建议先完成：

1. registry metadata 补齐
2. fundamentals snapshot adapter
3. quality/value long-row conversion
4. 主流水线拼接
5. score-stability 与缺失路径测试

等这一版稳定后，再单独评估：

- 是否接 `growth`
- 是否把 fundamentals 进入 `manual_v1`
- 是否进一步细化 `source_data_version` lineage
