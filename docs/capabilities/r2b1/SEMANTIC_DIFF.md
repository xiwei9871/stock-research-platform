# R2B → R2B.1 语义差集（真实结论变化）

基线：R2B `4725f4d3`（as_of 2026-10-23 相同快照口径重跑）。**所有真实变化均为降级或口径精化——无任何结论被升级。**

## 1. 商业兑现阶段变化（P0-A / P0-C）

| 节点/公司 | R2B confirmed_stages | R2B.1 | 原因 |
|---|---|---|---|
| humanoid_vision_sensing / 688686 | technology_demonstrated, revenue_attributed, profitability_visible | **[]**（demoted: technology_demonstrated） | 收入记录 `seg_688686_mv_2025FY` 产品线 key=`machine_vision` ∉ 节点线 `humanoid_vision`；4 条技术证据同样 pinned `machine_vision`（已列入 `out_of_scope_evidence_ids` 保留） |
| ai_power_liquid_cooling + liquid_cooling_pump_components / 603757 | customer_validated, commercial_delivery | **commercial_delivery** | 客户验证记录仅 `contact`+`mass_delivery`；`mass_delivery` 不再属验证车道（交付事实），无 `validated` 具名客户记录 |
| 其余公司（002837、301018、002050、002371、688037） | 不变 | 不变 | 002837 `customer_validated` 有具名客户 `validated` 记录（Intel），维持 |

## 2. 双重归属输出（新增维度）

| 公司 | product_line_attribution | theme_application_attribution | theme_specific_revenue |
|---|---|---|---|
| 688686 | confirmed | **unknown** | not_evaluated |
| 002837（三节点） | broader_scope_only | confirmed（具名客户验证在节点线） | not_evaluated |
| 301018 | broader_scope_only | unknown | not_evaluated |
| 603757 | missing | confirmed（交付在节点线） | not_evaluated |
| 002371 | broader_scope_only | unknown | not_evaluated |

`related_company_facts` 保留 `seg_688686_mv_2025FY`（机器视觉收入 9.6 亿、毛利 65.54%）——事实仍在，明确标注"非本主题场景"。

## 3. 认证/交付车道变化（P0-B）

| 公司 | R2B cert 值 | R2B.1 四事实 | 语义修正 |
|---|---|---|---|
| 603757 | `认证=mass_delivery` | product_certified / none_seen / contact / verified_delivered | mass_delivery 纯交付事实，不再冒充认证；UL 产品级认证归入 product_certification |
| 002837 | `认证=validated` | unknown / participating(或 out_of_node_scope) / validated / none_seen | NVIDIA MGX 生态独立为 ecosystem_participation，不再与客户验证合并 |
| 301018（cdu/coldplate 节点） | `认证=pending_review` | customer_validation=out_of_node_scope | 客户关系记录属 `dc_liquid_cooling` 线——如实标口径外，不再误导为未审核 |
| 301018（父节点） | `认证=pending_review` | customer_relationship_at_industry_board | 板块级客户关系披露如实标注口径 |

新增状态词：`out_of_node_scope`（合格记录存在但在其他产品线）、`out_of_pit`、`validated_unspecified_customer`、`customer_relationship_at_{scope}`。

## 4. CAP-07 同源判定变化（P1-D）

- `evidence_sources` 由 `{eid: source_id}` 升级为事实签名 `{src, dir, dim, scope, rev, sig}` 并纳入快照身份（使同源新事实可一次性吸收，而非反复报警）。
- 新分类：`duplicate_ingestion`（同源同事实重采→non_substantive）、`same_source_new_fact`（反证→material / 其他→notable）、`source_revision`（审核状态变化→minor；事实范围/方向变化→notable；方向翻转反证→material）。
- 旧规则"同 source_id 即 non_substantive"已废除——同一来源新事实不再被静默吞掉。

## 5. CAP-09 任务身份变化（P1-E）

- `task_id` 由顺序号 `vt-0001` 改为内容 hash `vt-<sha1前10>`（theme+company+question/hypothesis+required_evidence）——重跑/重排身份不变。
- 相同验证需求跨父子节点合并为单任务，`related_node_ids` 列出全部关联节点。
- ai_power 任务数 46 → **30**（跨节点重复需求合并），humanoid 27、semi 8。

## 6. 不变量

- CAP-01/02 冻结引擎与 `node_verdict` 零改动；PIT（as_of=2026-10-23）、幂等、research_only/used_for_signal=False/used_for_admission=False 全部保持。
- 无新 supported 结论；全部变化方向为"更严格的归属与更精确的状态词"。
