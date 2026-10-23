# R1 vs R2A 结构与结论差异报告

基线：R1 `f5155149` → R2A `feat/cap-r2-evidence-reasoning`（未提交时点产物对照）

## 1. 结构差异（新增字段，原字段全部保留）

| 能力 | R1 输出 | R2A 新增 |
|---|---|---|
| CAP-04 | `claim_roles` 视图 + evidence_index | `technical_assessment`{supply_constraint, non_substitutability, entry_barrier}，每区五项子判定 + 证据边界 |
| CAP-05 | margin_state / econ cells | `fact_positions`{revenue_disclosure, margin_disclosure, order_evidence, delivery_evidence, cash_collection} + `realization_state` |
| CAP-06 | 公司 verdict/状态罗列 | `pairwise_scope`（comparison_scope 四档）+ `scope_classes` + 同口径 `comparison` |
| CAP-07 | 快照（claim/econ/status） | 快照增加 `hypothesis_states`；幂等规则不变（派生字段仍排除） |
| CAP-08 | 五桶 + 三级追溯 | `hypothesis_assessment[]`（state/supporting/counter/alternatives/decisive_gaps/revision_triggers/independent_source_count/as_of） |
| pipeline | envelopes/per_node/gaps/workbench | `theme_synthesis`（findings/hypotheses/unresolved/next_verification/coverage） |
| CAP-09 | 五桶 + 公司格 + 缺口 | 节点“研究判断”区 + 主题“研究摘要”块 |

ResearchEnvelope 顶层契约不变：`capability_id`、`findings`、`evidence_refs`、`upstream_fingerprints`、as_of 语义全部保留。

## 2. 判定语义差异

| 场景 | R1 行为 | R2A 行为 |
|---|---|---|
| 多供应商证据 | market_structure 桶展示 | 同上 + 假设 `supported` 但 supply_constraint 不受影响；替代性另列 |
| 供给稀缺论点 | unresolved 桶 | `unresolved` + 替代解释“多供应商格局可吸收需求增长”+ 决定性缺口（capacity_or_leadtime/delivery_shortfall/supplier_count）+ 修订触发 |
| 认证壁垒论点 | unresolved 桶 | `unresolved` + 替代解释“产品级测试认证≠客户认证周期/成本壁垒” |
| hype 论点 | hype_risks 桶 | `risk_flagged` + 替代解释“主题映射/概念热度非供给/交付证据” |
| 公司比较 | 罗列 002837/301018 各自状态 | 002837×301018 `directly_comparable`；002371×688037 `partially_comparable`（母子公司） |
| 主题级结论 | 无 | theme_synthesis：4 节点发现 + 6 条竞争假设 + 13 未决 + 下一验证目标 |

## 3. 结论是否变化（诚实声明）

- **没有任何 R1 结论被升级**：所有 R1 `unverified`/`unresolved` 在 R2A 中保持同态；新增的是“为什么未决、缺什么、什么能改变它”。
- 唯一新增 `supported` 假设：`nc_multi_supplier` / `nc_nonexclusive_suppliers` / `nc_import_substitution_demand` —— 这三条在 R1 中已是 confirmed/partially_supported 的事实性论点，R2A 仅将其标注为假设层 supported，不构成投资价值结论。
- `nc_import_substitution_demand` supported ≠ “北方华创不可替代”——同假设块内替代解释与决定性缺口明确保留。
- CAP-01/02 引擎输出逐字节未变（契约测试锁定 node_verdict 不变性）。

## 4. 不变量

- research_only、used_for_signal=false、used_for_admission=false
- PIT/as_of 过滤、lead_only 降级、review_status 门槛保留
- 基线幂等：派生字段/元数据不参与身份（三连跑测试仍绿）
