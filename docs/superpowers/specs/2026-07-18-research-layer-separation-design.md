# Research Layer Separation Design

日期：2026-07-18

状态：方案已确认，等待书面规格复审后进入 R2A 实施计划

## 1. 目标校正

Research Operating Layer 后续不再把产业研究、公司映射和股票评价视为同一次研究中的连续字段填充，而是拆成三个具有独立身份、证据要求、状态和质量门槛的一等研究层：

```text
Industry Research
→ Company Solution And Value Capture Research
→ Stock Investment Evaluation
```

三层共同使用 R1 已交付的项目身份、不可变版本、事件流、命题、证据需求、证据评价、引用、因果关系、验证指标、失效条件和版本审计能力，但不共享结论对象，也不能绕过上游 Gate。

核心原则是：

> 先确认产业真实需要解决什么问题，再寻找谁有能力解决；先确认企业能够获得产业价值，最后才判断股票在当前价格上是否值得投资。

## 2. 架构选择

采用“共享研究内核 + 一等 `research_layer`”方案。

`research_layer` 枚举为：

```text
industry_research
company_capture
stock_evaluation
```

未采用：

- 一个通用项目加模块标记：边界过弱，容易让公司和股票结论提前进入产业研究；
- 三套完全独立的 artifact 根和公共模型：隔离最强，但会重复实现版本、证据、引用、事件和审计能力；
- 在现有 R1 pilot 中直接添加公司或股票字段：会改变已经冻结的 design baseline。

## 3. R1 兼容性

R1 的四个项目身份、`v0.1.0` version、manifest、index 和 schema baseline 保持不变，不重写、不迁移、不补写 `research_layer`。

R2 新建四个 `industry_research` 项目，分别引用 R1 pilot 的明确 `project_id + version_id + content_hash`，把 R1 设计作为输入基线，而不是原地升级历史快照。

兼容关系为：

```text
R1 design pilot v0.1.0
        ↓ immutable reference
R2 industry_research project
        ↓ Bottleneck Readiness Gate
R3 company_capture project
        ↓ Company Value Capture Gate
R5 stock_evaluation project
```

新层级字段只进入 R2 及后续的新 artifact/schema 版本。R1 loader 必须继续能够读取历史 `2.0.0` artifact。

### 3.1 Schema 演进规则

R2 采用 additive schema generation，不修改 R1 已提交的五个 `v2.schema.json` 文件：

```text
R1 artifact_version = 2.0.0
R2 layered artifact_version = 2.1.0
```

新增文件使用明确版本名，例如：

```text
definitions_v2_1.schema.json
research_project_identity_v2_1.schema.json
research_version_v2_1.schema.json
research_project_index_v2_1.schema.json
```

R2 identity 和 version 必须包含 `research_layer`。Loader 先读取顶层 `artifact_version`，再分派到 2.0 或 2.1 schema；不得用修改 R1 schema 的方式让旧 artifact 被新字段隐式解释。

R2 使用独立 artifact root，避免 R1 的四项目目录、index 和 rebuild 行为发生变化：

```text
artifacts/research_projects/v2_1/
├── schema/
├── projects/
├── evidence/
│   ├── raw/
│   ├── metadata/
│   └── normalized/
├── index/research_project_index_v2_1.json
└── fixtures/
```

R1 index 保持不变。R2 的 `research_project_index_v2_1.json` 只索引 layered projects。CLI 可以在读取时合并两个 index 的摘要，但不能把推断出的 `research_layer` 写入 R1 index，也不能让 R1 `rebuild-index` 扫描 `v2_1` 项目。

R2 layered project 使用统一的上游引用对象：

```text
upstream_research_ref_id
upstream_research_layer
upstream_project_id
upstream_version_id
upstream_object_type
upstream_object_id
upstream_gate_result_id
upstream_content_hash
referenced_at
scope_note
```

Industry Project 引用 R1 pilot 时，`upstream_research_layer` 使用 `null`，并明确 `scope_note=R1 unlayered design baseline`；不得把 R1 历史版本重新标记成 Industry Research 结论。

## 4. 通用研究内核

三个研究层共同复用：

- `research_project` 和 immutable `research_version`；
- scope、Router、question tree 和 stop conditions；
- claim、claim relation 和 counter claim；
- Evidence Requirement、Reference 和 Evidence Assessment；
- causal node、causal edge、validation metric 和 invalidation condition；
- provenance、content hash、manifest、event stream 和 diff；
- human review、version publication 和 reference drift audit。

通用内核不决定研究结论的类型。结论、Gate 和下游引用由 `research_layer` 决定。

## 5. Industry Research Layer

### 5.1 目标

建立不受上市公司名单和股票价格影响的产业事实模型，回答：

- 系统如何运行；
- 产品或服务如何制造、交付和使用；
- 哪些标准节点不可缺少；
- 哪些约束是真实瓶颈；
- 瓶颈为何形成、会持续多久、如何缓解；
- 瓶颈缓解后价值向哪里迁移；
- 哪些指标能够确认或推翻判断。

### 5.2 必需输出

```text
产业边界
→ 系统架构 / 制造流程 / 技术路线
→ 标准产业节点
→ 节点依赖与因果关系
→ 核心瓶颈
→ 瓶颈形成机制
→ 持续性与缓解条件
→ 供需与产业经济性
→ 价值迁移
→ 验证指标
→ 反方命题
→ 失效条件
```

### 5.3 禁止输出

Industry Research 不得生成：

- company rating；
- stock rating；
- 公司排名或股票池；
- 估值、目标价格、买卖建议；
- “某公司受益”作为未经验证的产业结论。

公司资料在本层只能作为工程案例、技术路线案例、产能案例、客户认证案例或产业证据来源。

## 6. Bottleneck Object

瓶颈是 Industry Research 的一等对象，不使用一个笼统的“卡脖子分数”。

`bottleneck_type` 至少支持：

```text
system
technology
process
material_equipment
supply_capacity
qualification_ecosystem
economics
```

`industry_bottleneck` 必需字段：

```text
bottleneck_id
target_node_ids
bottleneck_type
bottleneck_object
mechanism_summary
causal_edge_ids
affected_scope
severity
expected_duration
duration_basis
substitution_routes
mitigation_conditions
validation_metric_ids
invalidation_condition_ids
supporting_claim_ids
counter_claim_ids
evidence_requirement_ids
confidence
claim_status
lifecycle_status
provenance
```

`severity`、`expected_duration` 和 `confidence` 必须保留口径与依据，不能成为脱离事实的总分。

一个瓶颈可以被后续证据降级为 `contested`、`rejected` 或 `invalidated`。瓶颈失败不得污染 V1 或删除历史版本。

## 7. Industry Evidence Channel

Industry Evidence 重点证明系统、技术、工艺、供需和经济机制。

主要来源类型：

- 技术标准、论文和工程会议；
- 行业协会和监管资料；
- 产品、材料、设备和制造技术文档；
- 专利和检测资料；
- 供需、产能、价格和良率数据；
- 终端客户技术路线和资本开支；
- 专业产业研究；
- 公司披露中的工程、产能和认证事实。

Evidence Requirement 增加 `evidence_channel=industry`。产业命题不能用估值报告或股票观点作为核心支持证据。

## 8. Bottleneck Readiness Gate

只有通过 Bottleneck Readiness Gate 的瓶颈，才允许创建 `company_capture` 项目。

必需检查：

1. 产业边界明确；
2. 关键产业节点和依赖关系完整；
3. 瓶颈类型明确；
4. 形成机制和因果链闭合；
5. 至少存在一手、工程级或可复现数据证据；
6. 已完成反方与替代路线检索；
7. 严重程度和持续时间有依据；
8. 已定义替代方案与缓解条件；
9. 已定义 typed validation metrics；
10. 已定义 invalidation conditions；
11. 已说明瓶颈为何可能引发价值迁移；
12. 已区分“产业重要”与“利润可捕获”。

Gate 返回 `pass`、`pass_with_warnings`、`fail` 或 `not_applicable`，不使用单一总分。

Gate 的通过结果必须绑定明确的 `industry_project_id`、`industry_version_id` 和 `bottleneck_id`。后续证据使瓶颈失效时，系统产生 update event，不静默修改已启动的公司研究历史版本。

## 9. Company Capture Layer

### 9.1 启动条件

`company_capture` 项目必须引用：

- 一个已通过 Bottleneck Readiness Gate 的 Industry Research version；
- 一个或多个已通过的 `bottleneck_id`；
- 对应 Gate result 或人工审核记录。

没有通过 Gate 的“热点卡点”不能批量映射公司。

### 9.2 研究链

```text
bottleneck
→ required capability
→ technical solution routes
→ candidate companies
→ product evidence
→ qualification
→ effective capacity
→ order visibility
→ revenue conversion
→ profit conversion
```

### 9.3 Company Capability Stage

企业解决能力使用七级阶段，不直接等同于评分：

```text
1 concept_association
2 technology_patent_reserve
3 product_exists
4 sampling_or_qualification
5 effective_mass_production
6 order_and_revenue_visible
7 profit_contribution_realized
```

`company_capability_assessment` 至少记录：

```text
company_assessment_id
bottleneck_id
required_capability_id
company_reference_id
solution_route
capability_stage
product_evidence
specification_match
qualification_status
effective_capacity
yield_and_delivery
order_visibility
revenue_conversion
profit_conversion
independent_validation
counter_evidence
confidence
validation_metric_ids
invalidation_condition_ids
provenance
```

### 9.4 公司证据通道

Evidence Requirement 增加 `evidence_channel=company`，重点使用：

- 年报、招股书、交易所公告；
- 官网产品文档和技术规格；
- 客户、合作方、招投标和采购资料；
- 认证、送样和注册进度；
- 环评、设备采购、扩产、良率和有效产能；
- 订单、收入、毛利率和资本开支；
- 上下游独立交叉验证。

行业重要性不能替代公司产品、认证、有效产能、订单、收入和利润证据。

## 10. Company Value Capture Assessment

公司产业能力评价回答：

> 这家公司是否真正有能力解决产业问题并捕获产业价值？

评价对象包括：

- bottleneck match；
- technical barrier；
- commercialization stage；
- qualification and customer acceptance；
- effective capacity and yield；
- market share and competitive durability；
- revenue and profit materiality；
- persistence and substitution risk。

该层不得读取股票当前价格、估值倍数、交易拥挤度或目标价。Company Value Capture Gate 通过后，只能说明企业产业能力达到规定门槛，不能说明股票值得投资。

## 11. Stock Evaluation Layer

### 11.1 启动条件

`stock_evaluation` 项目必须引用：

- 已审核的 Company Capture version；
- 明确的 company assessment ID；
- Company Value Capture Gate result；
- 评价时点、市场价格和投资时间窗口。

### 11.2 独立评价对象

Stock Evaluation 在公司产业能力之外增加：

- 当前估值和历史区间；
- 市场已定价的增长与利润假设；
- 预期差；
- 催化事件与兑现时间；
- 上下行情景；
- 流动性、波动和交易拥挤度；
- 组合约束和风险预算。

公司产业能力评分和股票投资吸引力评分必须是两个独立对象。股票评价必须带 `as_of`、价格来源、币种、时间窗口、情景假设和失效条件。

## 12. 跨层引用与反馈

层级之间使用不可变版本引用：

```text
industry_project_id
industry_version_id
bottleneck_id
bottleneck_gate_result_id
```

```text
company_project_id
company_version_id
company_assessment_id
company_gate_result_id
```

下游不能修改上游版本。公司事实可以通过 `research_update_event` 反向触发 Industry Research 重审：

```text
industry research
→ bottleneck hypothesis
→ company evidence
→ industry update event
→ new industry version
```

反向反馈只能创建事件和新版本，不能自动提升瓶颈置信度，也不能产生股票排名。

## 13. Agent 职责隔离

一次 agent run 只能拥有一个主要 `research_layer`。

Industry agent 不得：

- 搜索股票排名或估值；
- 生成候选股票池；
- 给出 company/stock rating。

Company agent 不得：

- 修改已审核产业瓶颈；
- 用股价表现证明公司能力；
- 产生股票买卖建议。

Stock agent 不得：

- 绕过 Company Value Capture Gate；
- 把市场叙事当作产品、认证或利润证据；
- 回写上游 Industry 或 Company version。

跨层任务由 orchestrator 创建独立项目或版本，不允许一个 agent 同时完成三层结论。

## 14. 状态与 Gate

三个层级各自保留项目生命周期、证据状态和命题状态，不合并为单一 status。

Gate 顺序：

```text
Industry Design Gate
→ Industry Evidence Readiness Gate
→ Bottleneck Readiness Gate
→ Company Design Gate
→ Company Capability Evidence Gate
→ Company Value Capture Gate
→ Stock Evaluation Readiness Gate
→ Stock Publication / Strategy Gate
```

下游 Gate 只能消费明确的上游 Gate snapshot。Gate 失效时，下游项目进入 `upstream_revalidation_required`，不自动删除历史评价。

## 15. 路线图边界

### R2A：Industry Evidence Acquisition Baseline

优先建设 Search Plan、来源发现、抓取与快照、PDF/网页/数据集标准化、独立性、新鲜度、冲突检测和命题级 Evidence Assessment。

R2A 不实现公司评级、股票评级、生产数据库迁移、API 或 Dashboard。

### R2B：Industry Chain And Bottleneck Research

在四个差异化 pilot 上完成产业节点、因果关系、typed bottleneck、价值迁移、验证指标、反方命题和 Bottleneck Readiness Gate。

### R3：Company Solution Mapping

只从已通过 Gate 的瓶颈启动公司解决能力研究。

### R4：Company Value Capture Assessment

形成公司产业能力评价与 Gate，但不读取估值和股价。

### R5：Stock Investment Rating And Strategy Transmission

最后加入价格、估值、预期、催化、时间窗口、风险和交易因素。

## 16. R2A 第一阶段交付边界

R2A 首个实施计划只允许覆盖：

- `research_layer=industry_research` 的兼容 schema 设计；
- Industry Evidence Requirement 与 Search Plan；
- source discovery、snapshot、parse 和 normalize artifact contract；
- industry Evidence Assessment；
- source independence、freshness 和 conflict detection；
- 四个新 Industry Project identity/design version；
- 对 R1 pilot 的 immutable references；
- CLI、fixtures 和 tests；
- 无生产 migration 的 future DB mapping。

R2A 不实现：

- company candidate discovery；
- company capability stage；
- company rating；
- stock evaluation；
- watchlist 或 strategy transmission；
- API、Dashboard 或生产数据库写入。

## 17. 验收标准

本设计增量通过的标准：

1. R1 artifact 和四个 pilot 无修改；
2. 三个 `research_layer` 是一等项目边界；
3. Industry、Company、Stock 使用独立结论与 Gate；
4. bottleneck 是 typed first-class object；
5. Company Project 必须引用通过 Gate 的 bottleneck；
6. Stock Project 必须引用通过 Gate 的 company assessment；
7. 两套 rating 完全分离；
8. 公司事实只能通过 event/new version 反向更新产业判断；
9. R2A 实施范围只覆盖产业证据基础设施；
10. 本设计不授权生产 migration、API、Dashboard 或个股评级。
