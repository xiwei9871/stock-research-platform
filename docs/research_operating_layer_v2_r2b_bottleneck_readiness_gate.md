# Bottleneck Readiness Gate Specification

更新日期：2026-07-20

状态：R2B Phase 1 design。Gate 尚未实现，也未对任何 bottleneck 给出 ready 结论。

## 1. Purpose

Bottleneck Readiness Gate 判断一个已研究的产业瓶颈是否具备进入 R3 Company Solution Mapping 的条件。

Gate 不评价公司，不读取股价、估值或策略对象，不把产业重要性、证据数量或总分当作 readiness。

## 2. Preconditions

Gate 只接受：

- stored、immutable、lineage-verified Industry Research Version；
- status 非 `proposed` 的 `bottleneck_hypothesis`；
- 已通过 schema、semantic、hash、manifest、reference 和 evidence audit；
- evidence assessment 的 locator、independence、freshness 和 conflict 已验证；
- reviewer 使用真实 stored identity/version，不允许 unverified in-memory Gate。

Research Design Version 只能得到 `insufficient_evidence`，不能 ready。

## 3. Criteria

| ID | Criterion | Blocking | Pass condition |
|---|---|---:|---|
| `BRG-01` | 研究范围明确 | yes | product/application/geography/time/boundary 均明确 |
| `BRG-02` | Industry model 完整 | yes | 关键 architecture/process/lifecycle nodes 和 dependencies 已覆盖 |
| `BRG-03` | 瓶颈对象明确 | yes | target node/process 存在且 scope 唯一 |
| `BRG-04` | 形成机制完整 | yes | mechanism、affected parameter 和 impact path 可审计 |
| `BRG-05` | 因果链闭合 | yes | trigger→constraint→supply/demand/economics→outcome 有完整 edge |
| `BRG-06` | 技术约束与短期错配已区分 | yes | 有独立 counterfactual 和 duration hypothesis |
| `BRG-07` | 名义与有效产能已区分 | conditional | 涉及供给时必须有 qualified/yield/effective capacity 口径 |
| `BRG-08` | 高质量证据存在 | yes | 至少一条 primary/engineering/regulatory chain 直接支持 mechanism |
| `BRG-09` | 反方搜索完成 | yes | counter requirement、query coverage 和 assessment 均存在 |
| `BRG-10` | 来源实质独立 | yes | 支持链不依赖转载循环；family relationship 已审计 |
| `BRG-11` | 量化口径可解释 | yes | unit、denominator、time、product/geography 可比或差异已说明 |
| `BRG-12` | 替代路线已分析 | yes | substitution path、可行性、time lag 和 adoption condition 存在 |
| `BRG-13` | 缓解条件已定义 | yes | mitigation condition 可观察且关联 metric |
| `BRG-14` | 持续时间假设已定义 | yes | duration、time lag 和 review window 明确 |
| `BRG-15` | 验证指标已定义 | yes | leading/lagging metric、threshold、frequency、freshness 完整 |
| `BRG-16` | 失效条件已定义 | yes | threshold、persistence、minimum observations、recovery 完整 |
| `BRG-17` | 价值迁移机制已解释 | yes | value dimension、受益/受损节点、short-term/structural 区分 |
| `BRG-18` | 产业价值与公司捕获分离 | yes | 无公司名单/评分；只描述 required capability 类别 |
| `BRG-19` | 无提前公司或股票评级 | yes | Industry output taxonomy 和 scope audit 均通过 |

`BRG-07` 对不涉及产能的 regulatory/workflow bottleneck 可以 `not_applicable`，但必须有 reviewer reason。

### Criterion Result Rules

- `pass`：所有 required object/link/assessment/threshold 字段存在，且 reviewer decision 明确接受 scope/口径。
- `warning`：对象和证据链存在，但存在已结构化、非致命的 coverage/precision gap；必须创建 required next action。
- `fail`：required object/link/assessment 缺失，或 reviewer 明确认为机制/范围/口径不成立。
- `not_applicable`：只允许 criterion 明确声明 conditional，且 reviewer reason 非空。

对含“完整”“关键”“material”的 criterion，机器部分只判断对象、链接、数量、freshness 和 conflict flag；语义判断必须来自 reviewed criterion decision，不能由自由文本自动推断。

## 4. Deterministic Status Decision

先校验 `reviewer_decision` enum：`approve`、`approve_with_conditions`、`defer`、`reject`。decision 与 criteria/hypothesis 不一致时返回 Gate validation error，不生成 readiness review。

状态按以下优先级单选，命中后停止：

1. `rejected`：bottleneck status 为 rejected/invalidated、持久化 invalidation condition 已触发，或 reviewer decision=`reject` 且 reviewer 明确否定 mechanism。
2. `stale`：任一 blocking evidence chain stale，且尚未被 rejected。
3. `contested`：存在 material_conflict 或 reviewer 标记 mechanism unresolved，且尚未 rejected/stale。
4. `insufficient_evidence`：任一 blocking criterion 为 fail，或 reviewer decision=`defer`。
5. `conditionally_ready`：无 fail，至少一个 blocking criterion 为 warning，required next action 完整，且 reviewer decision=`approve_with_conditions`。
6. `ready`：所有 blocking criterion pass，conditional criterion pass 或有合法 not_applicable，且 reviewer decision=approve。

若全部 criteria pass 但 decision=`defer`，结果为 `insufficient_evidence`；若全部 pass 但 decision=`approve_with_conditions`，或存在 warning 但 decision=`approve`，输入不一致并返回 validation error。这样所有合法输入唯一落入一个状态。

### `ready`

- 所有 blocking criterion pass；
- 没有 material unresolved conflict；
- 所有关键证据未 stale；
- reviewer 明确批准进入 R3；
- bottleneck status 至少为 `provisionally_supported`，通常为 `confirmed_for_current_scope`。

### `conditionally_ready`

- 不允许任何 blocking criterion fail；
- 只允许 blocking criterion warning，且 warning 不得涉及 scope、对象、机制、反方搜索、产业/公司边界或股票边界；
- required next action 必须包含 `action_id`、`criterion_id`、`action_text`、owner、due_at、completion_condition 和 status；
- R3 只能做候选 capability discovery，不能形成公司评级。

### `contested`

- 形成机制有直接支持，但存在至少一条独立、实质反方证据链；
- 冲突不能通过 scope 或口径差异解释；
- 不得进入公司筛选。

### `insufficient_evidence`

- 缺失 primary/engineering/regulatory evidence；
- 证据只支持相关性，不能支持 mechanism；
- independence、coverage 或 quantity/supply/economics 口径不足。

### `stale`

- 任一 blocking evidence chain 超过 requirement freshness；
- 架构、政策、产能或价格已发生重大变化而未重审。

### `rejected`

- mechanism 被证伪；
- invalidation condition 已触发并满足 persistence；
- 候选瓶颈可由更简单的替代机制解释。

## 5. Output Contract

```text
bottleneck_readiness_review_id
gate_version
project_id
version_id
bottleneck_hypothesis_id
status
criteria_results[]
failed_criteria[]
warnings[]
unresolved_questions[]
evidence_gaps[]
required_next_actions[]
reviewer_decision
reviewed_by
reviewed_at
verified_scope
provenance
```

`required_next_actions` 是结构化对象数组，不是字符串数组：

```text
action_id
criterion_id
action_text
owner
due_at
completion_condition
status: open | complete | cancelled
```

`criteria_results` 必须包含 19 条结果。Gate 不返回总分。

`verified_scope` 只表示 stored identity/version/lineage/evidence 已验证；整体结果仍以 `status` 和 reviewer decision 为准。

## 6. Evidence Rules

- requirement presence 不等于 coverage；
- source presence 不等于 assessment；
- assessment presence 不等于 reviewed support；
- 多 URL 的同源转载只算一个 evidence family；
- evidence stance（supports/opposes/neutral）与 function（definition/context/mechanism/quantification/validation/invalidation/boundary）正交统计；
- background/context 不能满足直接 mechanism criterion；
- company primary source 可作为工程、产能或认证证据，但不能形成 company conclusion；
- 任何 stale blocking evidence 使 Gate 至少降级为 `stale`。

## 7. Reviewer Workflow

1. CLI 加载 stored project/version/bottleneck；
2. 完成 schema、semantic、hash、manifest、lineage 和 audit；
3. 逐条计算 machine-checkable criterion；
4. 输出 failed criteria、warnings、questions 和 gaps；
5. human reviewer 记录 decision；
6. review 作为 immutable object 进入新 version；
7. Gate 不自动修改 bottleneck status；状态变更需新 version 与 provenance。

## 8. Pilot Expectations

Phase 1 的 AI PCB 与 High-End Medical Device hypothesis 全部应为：

```text
status: proposed
Gate: insufficient_evidence
```

任何 Phase 1 design artifact 若显示 `ready`、`conditionally_ready` 或 `confirmed_for_current_scope`，均为验收失败。

## 9. Tests Required Before Implementation Acceptance

- 19 criteria exact coverage；
- design-only version cannot ready；
- missing counter evidence fails；
- republished sources do not satisfy independence；
- stale primary evidence returns stale；
- nominal capacity without effective capacity fails relevant criterion；
- material conflict returns contested；
- company/stock output fails BRG-18/19；
- no total-score shortcut；
- stored layout required and forged identity/version fails；
- immutable review and provenance lineage；
- R1/R2A artifacts remain byte-identical.
