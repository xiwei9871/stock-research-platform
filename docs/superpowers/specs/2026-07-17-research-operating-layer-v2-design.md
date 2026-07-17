# Research Operating Layer V2 Design

日期：2026-07-17

## 1. 目标

建立一个独立、领域无关、问题驱动的 Research Operating Layer，记录研究项目从问题定义、命题形成、证据需求、证据评价、因果推演、公司价值捕获验证到版本更新的全过程。

本设计不修改现有 27 个 Theme Research 主题、Technology Industry Catalog、Theme Research API 或 Dashboard，不执行生产数据库迁移。

## 2. 架构选择

采用 Independent V2 Artifact Layer。

未采用：

- 直接扩展 V1 Theme artifact：会混合知识资产和研究过程；
- 直接扩展 research_case：现有模型偏向交易日、股票和复盘工作流；
- DB-first：违反当前只读研究基线边界。

目标架构：

```text
V1 frozen knowledge assets
        ↓ typed references
Research Project / Research Operating Layer V2
        ↓ future version-bound adapters
research_case / review / publication / watchlist / strategy
```

## 3. 文件布局

```text
artifacts/research_projects/v2/
├── schema/
│   ├── definitions_v2.schema.json
│   ├── research_project_identity_v2.schema.json
│   ├── research_version_v2.schema.json
│   ├── research_event_v2.schema.json
│   └── research_project_index_v2.schema.json
├── projects/<project_slug>/
│   ├── project.json
│   ├── events/events.jsonl
│   ├── version_manifest.jsonl
│   └── versions/vX.Y.Z.json
├── index/research_project_index_v2.json
└── fixtures/{valid,invalid}/
```

CLI 不扫描任意 JSON 猜测含义。它只读取规定目录、identity、manifest 和 schema。

## 4. Identity、Version、Event 与 Index

### 4.1 Project Identity

`project.json` 是可更新的身份和指针文件：

```text
project_id
project_slug
title
purpose
created_at
created_by
current_lifecycle_state
current_version
latest_reviewed_version
latest_published_version
```

它不维护完整 version IDs，也不保存研究正文。

### 4.2 Research Version

版本文件是不可变完整快照：

```text
artifact_version
version_id
project_id
semantic_version
parent_version_id
creation_stage
created_at
created_by
change_summary
change_reason
incorporated_event_ids
content_hash
snapshot
```

`creation_stage`：

```text
research_design
evidence_snapshot
review_candidate
publication_snapshot
```

发布状态不回写版本文件，由 project pointer、publication record 和 event 表达。

### 4.3 Update Event

`events.jsonl` 是 append-only 权威事件流。事件可以在新版本形成前存在。

```text
event_id
project_id
event_type
triggered_at
trigger_source
affected_object_ids
base_version_id
proposed_action
review_status
resolution
incorporated_version_id
notes
provenance
```

### 4.4 Version Manifest

`version_manifest.jsonl` append-only 登记：

```text
version_id
semantic_version
parent_version_id
relative_path
content_hash
created_at
```

### 4.5 Index

Index 是可重建缓存，保存项目摘要和定位信息，不是权威研究内容。

## 5. 公共 Provenance

关键对象使用统一 provenance：

```text
created_by
actor_type
agent_run_id
created_at
created_in_version
review_status
```

`actor_type`：

```text
human
codex
automated_pipeline
imported
```

## 6. Scope 与 Router

### 6.1 Project Scope

```text
primary_question
research_object
included_scope
excluded_scope
geography
time_horizon
industry_boundary
company_universe_boundary
decision_context
assumptions
known_unknowns
stop_conditions
```

### 6.2 Router Decision

```text
primary_method
secondary_methods
routing_reasons
required_research_modules
excluded_modules
confidence
manual_override
override_reason
decided_by
decided_at
```

Router 选择研究模块，不给 Theme 永久贴标签。

方法包括 system architecture、manufacturing process、complex system、engineering scale-up、technology route、infrastructure economics、lifecycle、regulation 和 platform ecosystem。

## 7. Question Model

`research_question` 只保存问题内容和研究属性，不保存父节点。

```text
question_id
question_type
question_text
priority
required_for_gate
answer_status
linked_claim_ids
linked_requirement_ids
provenance
lifecycle_status
```

`question_tree_node` 保存视图和依赖：

```text
tree_node_id
tree_id
question_id
parent_tree_node_id
order
branch_role
dependency_question_ids
```

父节点表达展示层级，dependency 表达研究先后。Dependency graph 必须是 DAG。同一批问题可用于 research logic、evidence collection 和 publication outline 三类树。

## 8. Claim Model

所有命题统一使用 `research_claim_v2`：

```text
claim_id
claim_kind
epistemic_type
claim_text
claim_status
lifecycle_status
confidence
importance
linked_question_ids
context_reference_ids
created_in_version
supersedes_claim_id
validation_metric_ids
invalidation_condition_ids
provenance
```

`claim_kind`：primary、supporting、counter、alternative、boundary。

`epistemic_type`：fact、interpretation、hypothesis、forecast。

`context_reference_ids` 只能用于 definition、background 和 scope context，不能表达证据支持。

`claim_relation`：

```text
relation_id
from_claim_id
to_claim_id
relation_type
relation_summary
created_in_version
provenance
```

关系包括 supports、challenges、contradicts、narrows、qualifies、alternative_to、depends_on 和 supersedes。

## 9. Evidence Model

### 9.1 Evidence Requirement

```text
requirement_id
target_type
target_id
question_to_resolve
requirement_type
required_source_classes
required_independence
required_freshness
required_scope
minimum_coverage
conflict_search_required
primary_source_required
collection_status
satisfaction_status
provenance
```

Target 可以是 project、question、claim、causal edge 或 company capture。

### 9.2 Reference

```text
reference_id
reference_namespace
reference_type
reference_object_id
reference_role
reference_version
reference_content_hash
hash_scope
referenced_at
locator
scope_note
resolution_status
provenance
```

Namespaces 包括 theme_research_v1、industry_catalog_v1、evidence_artifact、research_case、external_document、dataset、web_resource、company_filing、manual_interview 和 api_snapshot。

### 9.3 Evidence Assessment

```text
assessment_id
target_type
target_id
requirement_id
reference_id
evidence_role
locator
assessment_summary
directness
strength
independence
freshness
scope_match
conflict_status
review_status
provenance
```

来源与命题之间的实质性关系只能通过 Evidence Assessment 表达。

## 10. Causal Model

`causal_node` kinds：trigger、change、system_parameter、mechanism、constraint、demand_effect、supply_effect、price_effect、competition_effect、value_migration、company_capture、outcome。

`causal_edge`：

```text
causal_edge_id
from_causal_node_id
to_causal_node_id
relation_type
mechanism_text
effect_polarity
strength
confidence
time_lag
boundary_condition
feedback_loop_id
supporting_claim_ids
validation_metric_ids
lifecycle_status
provenance
```

问题依赖图禁止环。因果图允许显式 feedback loop。

## 11. Validation 与 Invalidation

### 11.1 Validation Metric

```text
metric_id
target_type
target_id
metric_name
metric_definition
data_source_plan
unit
baseline_value
baseline_as_of
comparison_operator
observation_window
aggregation_method
expected_range
confirmation_threshold
warning_threshold
data_freshness_requirement
observation_frequency
status
provenance
```

### 11.2 Invalidation Condition

```text
condition_id
target_type
target_id
condition_text
observable_test
comparison_operator
threshold_value
unit
persistence_window
minimum_observations
recovery_condition
severity
status
triggered_at
provenance
```

## 12. Company Capture

```text
assessment_id
company_reference_id
node_reference_ids
capture_stage
product_evidence_status
qualification_status
capacity_status
order_status
revenue_conversion_status
profit_conversion_status
market_pricing_status
linked_claim_ids
linked_requirement_ids
assessment_status
provenance
```

兑现阶段：concept exposure、product exists、qualification、capacity ready、order visibility、revenue conversion、profit conversion。

首批 design artifact 只定义未来检查需求，不填写验证结果。

## 13. 跨版本身份和 Diff

语义未变时保留对象 ID；状态、置信度和轻微文字修订不创建新 ID。语义、方向或适用范围实质变化时创建新 ID，并通过 supersedes 关系连接旧对象。

对象不能从历史版本删除。新版本可标记 active、retired、superseded 或 removed_from_scope。

Diff 分类：added、removed_from_current_scope、modified、status_changed、superseded、unchanged。对象身份只按 ID 判断，不使用文本相似度猜测。

## 14. 状态机

### 14.1 Project

proposed → scoped → research_ready → active → review_ready → published。

允许 review_ready → active、published → active、published → superseded、非终态 → archived。

### 14.2 Evidence

not_started → requirements_defined → collecting → partially_covered → sufficient_for_review → stale。

Stale、partially covered 和 sufficient for review 均可回到 collecting。

### 14.3 Claim

hypothesis → under_test → supported / contested / rejected。Supported 或 contested 可进入 invalidated。

Claim 状态与 lifecycle status 分离。

### 14.4 Conclusion 和 Investment

Conclusion：unavailable、provisional、review_ready、reviewed、published、withdrawn、invalidated。

Investment：not_assessed、research_only、watchlist_candidate、strategy_hypothesis、rejected。

首批项目必须是 conclusion unavailable 和 investment not assessed。

## 15. Quality Gates

### 15.1 Research Design Gate

检查具体问题、scope、Router、有效问题树、DAG、关键问题和命题的 evidence requirements、反方命题、验证计划、失效条件、引用解析、provenance 和 hash。

首批 artifact 禁止 supported claim、已满足证据需求、已验证 company capture、published conclusion 和投资判断。

### 15.2 Evidence Readiness Gate

检查关键 requirement 覆盖、直接证据、一手来源、独立来源、反方检索、转载循环、freshness、assessment、因果边支持、reference drift 和 company capture stage。

### 15.3 Publication Gate

检查因果链闭合、事实/解释/假设/预测区分、反方处置、量化、公司兑现、typed metrics、invalidation、人工审核和无关键 drift。

Gate 返回 pass、pass_with_warnings、fail 或 not_applicable，不使用单一总分。

## 16. JSON Schema 与 Semantic Validation

Schema 文件负责结构、required、enum、格式和基础类型。

Python semantic validator 负责：

- ID 唯一性；
- 跨对象引用；
- DAG；
- 因果 feedback 标记；
- 状态转换；
- Gate；
- content hash；
- manifest immutability；
- reference drift；
- 首批 research-design 限制。

## 17. Hash 规范

算法为 `sha256-jcs-v1`：SHA-256 over RFC 8785 canonical JSON，UTF-8，禁止 NaN/Infinity，时间戳写入前规范为 UTC RFC 3339。

Version hash 排除顶层 content_hash 自身，其余字段参与 hash。Reference hash scope 必须是 entire_object、selected_fields、source_content 或 metadata_only。Selected fields 必须保存字段路径。

## 18. CLI

```text
research-project-v2 list
research-project-v2 show --project ID [--version VERSION]
research-project-v2 validate [--project ID] [--version VERSION] [--all]
research-project-v2 summary [--project ID]
research-project-v2 audit-references --project ID [--version VERSION]
research-project-v2 diff --project ID --from VERSION --to VERSION
research-project-v2 gate --project ID --version VERSION --gate design|evidence|publication
```

退出码：0 成功；2 schema/semantic failure；3 reference audit failure；4 gate failure；5 immutability/hash failure；6 not found；7 invalid diff ancestry/identity；10 runtime/I/O failure。

## 19. Reference Drift

状态：resolved、missing、type_mismatch、version_mismatch、hash_mismatch、deprecated、duplicate、unresolvable。

Drift 不修改历史版本。当前版本发现 drift 后创建 update event，由人工选择接受新引用、保留旧引用、缩小范围、标记失效或有理由地忽略。

## 20. 首批四个 Artifact

统一状态：creation stage research_design、project stage research_ready、evidence stage requirements_defined、conclusion unavailable、investment not assessed。

- AI 算力 PCB：system architecture + manufacturing process。
- 人形机器人：complex system + engineering scale-up。
- 新型储能：technology route + infrastructure economics。
- 高端医疗器械：lifecycle + regulation + system architecture。

它们只定义问题、Router、问题树、hypothesis、evidence requirements、validation plan 和 references，不产生完成的产业结论。

## 21. Future Database Mapping

未来表：project、version、version snapshot、event、reference、project-theme、question、tree node、dependency、claim、claim relation、evidence requirement、evidence assessment、causal node、causal edge、metric、invalidation、company capture 和 publication event。

Version snapshot append-only，禁止 update/delete。V1 默认软引用；若未来使用 FK，只允许 RESTRICT/NO ACTION。research_case adapter 必须绑定明确 project_id 和 version_id。

## 22. 未解决决策

1. RFC 8785 使用依赖还是内部实现。
2. JSONL event 与独立 event 文件的取舍。
3. 动态网页/API 的长期归档方式。
4. 第一阶段 resolver namespace 范围。
5. Counter claim 是覆盖全部 primary claim 还是只覆盖关键命题。
6. Company capture 从哪个阶段开始必填。
7. research_case adapter 是否允许状态回传。
8. Reviewed/published 权限模型。
9. Publication snapshot 文件结构。
10. 项目拆分、合并和跨项目 claim 引用。
11. Artifact 数量和索引性能边界。
12. Future Promotion 的人工审核和目标知识库。

## 23. 当前阶段验收

本设计阶段完成后，不实现 V2 代码。下一步必须由用户审核书面 spec。审核通过后，使用 writing-plans 生成实施计划；实施计划第一阶段仅覆盖 artifact baseline、loader、CLI、fixtures、四个 research-design artifact 和测试，不包含生产 migration、API 或 Dashboard 改造。
