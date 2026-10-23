# R2A → R2B 结构与判断差异

基线：R2A `57fd9b9a` → R2B（本分支 HEAD）

## 1. 结构差异

| 能力 | R2A | R2B |
|---|---|---|
| CAP-04 | 三评估区+证据边界 | 不变（仅 hypothesis 来源字段细化） |
| CAP-05 | 五事实位 + `commercialization_stage` 粗标签 | `commercialization_assessment`：六阶段 stage_evidence/confirmed/missing/attribution_scope/source_ids；粗标签保留 |
| CAP-06 | comparison + pairwise_scope | 公司行新增 `certification_customer_validation`(认证车道) / `delivery_capability`(交付车道) / `product_maturity` / `cert_delivery_record_ids`——两车道独立证据 |
| CAP-07 | 增删改 diff | 每条 change 增加 `change_category / materiality / affected_hypothesis_ids / before / after / evidence_delta / explanation / action_required` + `materiality` 汇总 |
| CAP-08 | hypothesis_assessment | 新增 `supporting_source_count / counter_source_count / support_source_ids / counter_source_ids`；`independent_source_count` = 正反合计去重 |
| 快照 | claims/hypotheses/econ/evidence_refs | 增加 `evidence_sources`（排除出内容身份）+ econ `stages` |
| 工作台 | 研究判断区+主题摘要 | +验证任务清单（proposed）+认证/交付/兑现阶段列+变化分级 |

ResearchEnvelope 顶层契约、五桶、claim_roles 视图全部保留。

## 2. 判断差异（审核发现的真实修正）

| 项 | R2A | R2B | 性质 |
|---|---|---|---|
| 002837 交付 | `validated`（验证阶段误作交付） | `none_seen` | **修正**：验证证据不再冒充交付 |
| 002837 认证 | （同字段复用） | `validated` | 新字段正确归因 |
| 301018 认证/交付 | none_seen/none_seen | `pending_review`/none_seen | 更诚实：有未审核记录≠无记录 |
| 603757 兑现 | （未展示） | customer_validated+commercial_delivery | 组件级兑现首次可见，但未归属收入 |
| independent_source_count | 仅支持来源 | 正反合计去重 | 口径修正，数值对多支持假设不变 |
| 快照 as_of | 2026-10-31/28（未来请求时点） | 2026-10-23 | PIT 合规正式快照 |

## 3. 无变化声明

- 所有假设 assessment_state 与 R2A 一致（未升级任何结论）
- node_verdict、CAP-01/02 判定逐字节不变
- 五桶成员、research_only、信号/准入标志不变
