# Research Operating Layer V2 R2B Minimum Schema Extension Proposal

更新日期：2026-07-20

## 1. Status

本文件是 Phase 1 proposal，不是已实现 schema。当前不修改 JSON Schema、loader、semantic validator、CLI、artifact 或数据库。

## 2. Design Rules

扩展必须满足：

- additive-only；
- 旧 R2A `v0.1.0` artifacts 无需迁移且继续验证；
- 新对象只属于 `industry_research`；
- 不允许 company capture、stock evaluation、watchlist 或 strategy output；
- 所有对象保留 stable ID、provenance、lifecycle 和 immutable version 语义；
- 新 target 必须经过 semantic reference validation；
- Gate review 不能自动改变 hypothesis status；
- 本 proposal 不增加数据库表。

## 3. Router Extension

向 `research_method` enum additive 增加：

- `constraint_analysis`
- `commercialization`
- `value_migration`

不删除或重命名既有值。

## 4. Industry Model

### 4.1 `industry_model_node`

```text
industry_model_node_id
model_id
node_type
title
description
scope_note
key_parameters
lifecycle_status
provenance
```

`node_type`：

```text
system_component
process_step
lifecycle_stage
material
equipment
input
output
market_interface
regulatory_stage
ecosystem_service
```

### 4.2 `industry_model_edge`

```text
industry_model_edge_id
model_id
from_industry_model_node_id
to_industry_model_node_id
relation_type
dependency_criticality
flow_or_dependency_text
time_lag
boundary_condition
supporting_claim_ids
counter_claim_ids
lifecycle_status
provenance
```

`relation_type`：`contains`、`feeds`、`depends_on`、`transforms`、`qualifies`、`enables`、`constrains`、`substitutes`、`flows_to`。

理由：因果边要求 polarity、strength 和 mechanism，不能无损表达 BOM 归属、制造顺序、生命周期先后或普通依赖。

## 5. Bottleneck Hypothesis

新增 `bottleneck_hypothesis`：

```text
bottleneck_hypothesis_id
title
bottleneck_type
target_node_or_process_id
scope
mechanism
affected_system_parameter_ids
impact_path_edge_ids
severity_hypothesis
duration_hypothesis
substitution_paths
mitigation_conditions
supporting_claim_ids
counter_claim_ids
evidence_requirement_ids
validation_metric_ids
invalidation_condition_ids
status
confidence
lifecycle_status
created_in_version
provenance
```

`target_node_or_process_id` 必须引用 `industry_model_node_id`。`affected_system_parameter_ids` 必须引用 `causal_node_id`，且目标 `node_kind=system_parameter`。`impact_path_edge_ids` 必须引用 `causal_edge_id`，不允许混用 industry dependency edge。

`bottleneck_type`：

```text
system
technical
process
material
equipment
effective_capacity
supply_chain
qualification
regulatory
software_ecosystem
economic
short_term_supply_demand
```

`status`：

```text
proposed
under_investigation
provisionally_supported
contested
confirmed_for_current_scope
rejected
stale
invalidated
```

禁止无范围的 `confirmed`。

## 6. Value Migration Analysis

新增 `value_migration_analysis`：

```text
value_migration_analysis_id
bottleneck_hypothesis_id
scope
affected_node_ids
beneficiary_node_ids
disadvantaged_node_ids
dimensions
structurality
mechanism_summary
supporting_claim_ids
counter_claim_ids
evidence_requirement_ids
validation_metric_ids
status
confidence
lifecycle_status
provenance
```

`dimensions` 必须逐项允许 `increase`、`decrease`、`mixed`、`unchanged`、`unknown`，并保存 explanation：

- quantity
- content_per_system
- unit_price_or_asp
- penetration_rate
- market_share
- gross_margin
- capital_intensity
- working_capital
- replacement_cycle
- supplier_concentration
- switching_cost
- qualification_cost

`affected_node_ids`、`beneficiary_node_ids` 和 `disadvantaged_node_ids` 均只引用 `industry_model_node_id`；同一 node 可以出现在 affected 与 beneficiary/disadvantaged 中，但不得同时出现在 beneficiary 与 disadvantaged，除非该 dimension 明确标记 `mixed`。

`structurality`：`short_term`、`mixed`、`structural`、`unknown`。

## 7. Bottleneck Readiness Review

新增 immutable `bottleneck_readiness_review`：

```text
bottleneck_readiness_review_id
gate_version
project_id
version_id
bottleneck_hypothesis_id
status
criteria_results
failed_criteria
warnings
unresolved_questions
evidence_gaps
required_next_actions
reviewer_decision
reviewed_by
reviewed_at
verified_scope
provenance
```

`required_next_actions` item：

```text
action_id
criterion_id
action_text
owner
due_at
completion_condition
status: open | complete | cancelled
```

`status`：`ready`、`conditionally_ready`、`contested`、`insufficient_evidence`、`stale`、`rejected`。

`reviewer_decision`：`approve`、`approve_with_conditions`、`defer`、`reject`。decision 与 status 的一致性由 Gate semantic rules 强制：`approve` 只能产生 `ready`；`approve_with_conditions` 只能产生 `conditionally_ready`；`defer` 产生 `insufficient_evidence`（除非更高优先级为 stale/contested）；`reject` 只能在 hypothesis rejected/invalidated 或 reviewer 明确否定 mechanism 时产生 `rejected`。不一致输入视为 Gate validation error，不写 review artifact。

每条 `criteria_result`：

```text
criterion_id
status: pass | fail | warning | not_applicable
reason
claim_ids
assessment_ids
metric_ids
```

不保存总分，不根据分数自动晋级。

## 8. Target Type Extension

Industry-only target enum additive 增加：

- `industry_model_node`
- `bottleneck_hypothesis`
- `value_migration_analysis`

适用于：

- evidence requirement；
- common/industry evidence assessment；
- conflict summary；
- validation metric；
- invalidation condition。

`company_capture` 继续禁止出现在 Industry profile。

### 8.1 Evidence Stance And Function

R2B 不继续把“立场”和“用途”塞入一个单值 `evidence_role`。2.2 assessment 新增两个正交 required 字段：

```text
evidence_stance: supports | opposes | neutral
evidence_function:
  definition | context | mechanism | quantification |
  validation | invalidation | boundary
```

例如一份反方机制证据可表达为 `opposes + mechanism`。旧 2.1 assessment 的 `evidence_role` 不迁移；2.2 使用独立 assessment schema。`neutral + context` 不得满足直接支持或 readiness mechanism criterion。

## 9. Evidence Requirement Extension

现有字段保留。可选增加：

```text
geography_scope: string[]
product_scope: string
stop_conditions: string[]
required_evidence_stances: string[]
  items: supports | opposes | neutral
required_evidence_functions: string[]
  items: definition | context | mechanism | quantification |
         validation | invalidation | boundary
lifecycle_status: active | retired | superseded | removed_from_scope
supersedes_requirement_id: string | null
```

理由：`required_scope` 自由文本不能稳定审计 geography、product boundary 和 requirement-level stopping rule。

不把“文章数量”加入完成度定义。`minimum_coverage` 表示独立证据链或规定口径覆盖，而不是 URL 数量。

## 10. Causal Edge Extension

向 `causal_edge` 增加可选：

```text
counter_claim_ids: string[]
```

现有 `supporting_claim_ids` 保持不变。R2B Gate 对关键 edge 要求至少存在 counter claim 或明确的 `not_applicable` 理由。

## 11. Schema Version And Snapshot Collections

R2B 新 version 使用 `schema_version: 2.2.0`，不把新字段或 enum 静默塞进 `2.1.0` contract。

实现新增：

```text
definitions_v2_2.schema.json
industry_research_version_v2_2.schema.json
industry_evidence_assessment_v2_2.schema.json
```

2.2 definitions 可 `$ref` 2.1 中完全未变化的 scalar/utility definition，但任何扩 enum 或新增字段的 object 必须在 2.2 中独立定义。loader 按 `schema_version` 选择 validator。旧 `2.1.0` schema 和四个 R2A version 不迁移、不重写。

2.2 Industry snapshot 增加以下 required arrays：

```text
industry_model_nodes
industry_model_edges
bottleneck_hypotheses
value_migration_analyses
bottleneck_readiness_reviews
```

旧 2.1 version 不包含这些字段时仍合法。R2B 2.2 version 要求五个 arrays 显式存在，即使为空。

## 12. Research Update Event Gap — Deferred

当前 version 有 `incorporated_event_ids`，但没有项目级 append-only event artifact。该能力不是 Phase 2 最低路径的阻塞项：

- `v0.2.0` 与 `v0.3.0` 暂时保持 `incorporated_event_ids: []`；
- change summary、provenance、immutable evidence artifact 和 diff 提供本轮审计链；
- 不允许用 artifact/assessment ID 冒充 event ID。

只有用户另行批准后才考虑以下事件对象：

```text
research_update_event_id
project_id
event_type
occurred_at
observed_at
reference_ids
artifact_ids
assessment_ids
impact_summary
review_status
disposition
provenance
```

`disposition`：`pending_review`、`incorporated`、`ignored`、`superseded`。

事件存储应为 project-level append-only JSONL。它不进入当前最低 Phase 2 implementation plan。

## 13. Stable-ID Diff Gap

V2.1 需要复用 R1 diff 语义并增加 object families：

- industry model nodes/edges；
- bottleneck hypotheses；
- value migration analyses；
- readiness reviews；
- evidence assessments；
- causal nodes/edges；
- validation metrics；
- invalidation conditions。

输出分类至少为：`added`、`modified`、`status_changed`、`removed_from_current_scope`、`superseded`、`unchanged`。

CLI 只需扩展必要入口：

```text
research-project-v2-1 diff --project ... --from ... --to ...
research-project-v2-1 gate --gate bottleneck-readiness --bottleneck ...
```

## 14. Compatibility Path

推荐实现顺序：

1. 先以测试证明四个旧 R2A version bytes 和 validation 结果不变；
2. 新增隔离的 2.2 definitions/version/assessment schemas；
3. loader 同时支持 2.1.0 和 2.2.0；
4. semantic validator 只对 2.2 profile 要求新 collections；
5. 新对象进入 ID uniqueness、reference resolution、provenance lineage 和 diff；
6. 不迁移旧 artifact，不重写 manifest/index；
7. 新建 `v0.2.0 research_design`，而不是覆盖 `v0.1.0`。

## 15. Decision Required

Phase 2 前需要用户确认：

- 是否批准 `schema_version 2.2.0` 与五个新 snapshot collection；
- 是否同意 research update event 暂缓，`incorporated_event_ids` 保持空；
- 是否批准 `v0.2.0 design -> v0.3.0 review_candidate` 的双版本路线；
- 是否批准只增加 `diff` 和 `bottleneck-readiness` 两个必要 CLI 能力。
