# CAP-R2B.1｜商业兑现归属与证据语义收口 — 审计报告

- **仓库**：`xiwei9871/stock-research-platform`
- **分支**：`fix/cap-r2b1-evidence-scope`
- **基线**：R2B `4725f4d3341bb091c5607d632e48a475d148f61c`
- **快照口径**：as_of ≤ 2026-10-23（与 R2B 正式快照一致）

## 1. 五项修复与真实链路验证

### P0-A 产品线与主题场景双重归属 ✅

CAP-05 增加三维归属：`product_line_attribution` / `theme_application_attribution` / `theme_specific_revenue`（恒 `not_evaluated`），并在 `related_company_facts` 中保留"成立但不归本主题"的事实。

**688686 实证**：机器视觉收入/毛利记录 `seg_688686_mv_2025FY`（key=`machine_vision`）不再被记作人形节点兑现 → `product_line_attribution=confirmed, theme_application_attribution=unknown`；R2B 中 `revenue_attributed`/`profitability_visible` 两阶段已撤下，记录完整列入 `related_company_facts`。跨产品线复用审计覆盖全部三主题——液冷父子节点（英维克/申菱/大元）均只计本节点产品线 key 的收入。

### P0-B 认证/交付四事实分离 ✅

`_cert_delivery_split` 输出四个独立事实位：

| 事实 | 证据阶梯 |
|---|---|
| `product_certification` | 产品级认证披露（UL 认证、产品测试完成） |
| `ecosystem_participation` | 生态/合作伙伴参与（NVIDIA MGX 认证、进入生态链） |
| `customer_validation` | 具名客户验证阶梯（lead→contact→testing→…→validated→certified） |
| `commercial_delivery` | 纯交付证据（交付/量产记录） |

`mass_delivery` 只进入交付事实。**大元泵业实证**：R2B `认证=mass_delivery` → R2B.1 `产品认证=product_certified · 生态=none_seen · 客户验证=contact · 交付=verified_delivered`；组件交付保留，CDU 系统级客户认证不推定。英维克 `生态=participating`（NVIDIA MGX）与 `客户验证=validated`（Intel）独立呈现；生态参与不再冒充具名客户验证。

### P0-C 阶段级证据追溯 Gate ✅

六阶段统一 Gate：每条计入证据携带 `record→source→review→scope→as_of` 五元 trace，经资格集合 + PIT + 产品线归属 + 证据资格四重过滤；confirmed 阶段若无存活直接证据 → 降级入 `demoted_stages`。`out_of_scope_evidence_ids` 保留被排除证据引用。

**688686 实证**：`technology_demonstrated` R2B confirmed（空引用）→ 降级，4 条技术证据全部 `related_company=machine_vision`——如实标注"证据仅覆盖其他产品线"而非笼统无证据。`stage_trace_audit.csv` 列出三主题全部 72 个 stage×公司 组合的 trace 完整性。

### P1-D CAP-07 同源新事实判定 ✅

`evidence_sources` 快照升级为事实签名（source+方向+维度+范围+审核+事实指纹，纳入身份）。新增分类：`duplicate_ingestion`（同源同事实重采，non_substantive）、`same_source_new_fact`（新合格反证→material，其他→notable）、`source_revision`（审核态变化→minor，事实范围变化→notable，方向翻转→material）。同一来源不再被 source_id 一刀切吞掉。

### P1-E CAP-09 稳定任务身份 ✅

`task_id` = SHA1(theme+node+company+hypothesis+required_evidence)[:10]。重复运行/任务重排 ID 不变；跨父子节点相同验证需求合并为单任务 + `related_node_ids`。`stable_task_ids.json` 记录三主题 30/27/8 条任务全量 ID 快照。

## 2. 验收七场景覆盖

| 场景 | 验证方式 | 结果 |
|---|---|---|
| 688686 机器视觉收入披露、人形收入未知 | 契约测试 + 真实链路 | ✅ 双重归属输出 |
| 大元组件交付 ≠ CDU 系统交付/认证 | 契约测试 + 真实链路 | ✅ 四事实分离 |
| 产品测试/生态 ≠ 具名客户验证 | `test_r2b1_cert_four_facts_split` | ✅ |
| 无有效证据引用的 confirmed 降级 | `test_r2b1_stage_gate_trace` + 真实链路 | ✅ |
| 同源重复采集不触发实质事件 | `test_r2b1_same_source_duplicate_ingestion` | ✅ non_substantive |
| 同源新增合格反证触发变化 | `test_r2b1_same_source_new_fact` | ✅ material |
| 任务 ID 重排/重跑稳定 | `test_r2b1_stable_task_id_*`（3 个） | ✅ |

## 3. 测试

- `tests/test_capabilities.py`：**51 绿**（44 R2B + 7 R2B.1）
- capability 聚焦面：**406 绿**
- 前端 **443 绿** + `pnpm build` 通过
- 全量回归：见 `REGRESSION_DIFF.md`（与 R1 基线差集 = 0）

## 4. 交付物

`r2b1_*.json`（三主题快照）、`cap05_attribution_checklist.csv`（归属对照）、`stage_trace_audit.csv`（阶段证据追溯）、`stable_task_ids.json`（任务 ID 快照）、`uat_*_r2b1.png`（三截图）、`SEMANTIC_DIFF.md`、`REGRESSION_DIFF.md`、本报告。

## 5. 遗留说明

- `theme_specific_revenue` 恒 `not_evaluated`：T3 数据集无"场景级收入"记录类型（如"人形机器人收入"单列分部），需要新数据类型才能评估——不虚构。
- `customer_validation` 依赖 `customer_name` 字段：具名客户验证只认有客户名的记录；`validated_unspecified_customer` 如实标注"已验证但客户未具名"。
- 未部署、未合 main、research_only、无信号/准入变更、未干扰 DATA-R3-P1c。
