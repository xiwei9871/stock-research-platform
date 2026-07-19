# R2B Pilot Design — High-End Medical Device Commercialization

更新日期：2026-07-20

状态：Phase 1 research design。所有瓶颈均为待验证 hypothesis，不是国产替代或商业化结论。

## 1. Scope Confirmation

### Primary Question

高端医疗器械从技术和注册可用走向规模商业化时，真正限制医院采用、活跃使用和持续收入的环节是什么？

### Research Object

研究对象不是“所有医疗器械”，而是高资本支出、需要注册/临床证据、医院准入、医生培训、安装维护或耗材/软件生态的高端设备商业化漏斗。

### Included Scope

- 研发验证、产品性能和 clinical value；
- 注册路径、临床证据和监管审评；
- 医院预算、准入、招标、采购、安装与验收；
- 医生学习成本、workflow integration、科室协作和使用习惯；
- active installed base、检查/手术量、开机率和设备利用率；
- 售后响应、维护、备件、软件升级和耗材生态；
- 支付、回款、全生命周期成本和经济性；
- 国产产品“存在—获批—中标—安装—活跃使用—持续收入”的转化差距。

### Product Stratification Rule

所有证据至少按以下维度分层，不允许直接混合：

- risk class / registration path；
- diagnostic、therapeutic、surgical、imaging 或 laboratory workflow；
- capital equipment 与 equipment-plus-consumables；
- new installation 与 replacement；
- public hospital tier、specialty 和 geography；
- 单机销售、service contract、consumable 和 software revenue。

### Excluded Scope

- 公司名单、公司商业能力评分和股票评价；
- 用获批数量、产品注册证数量或“国产率”直接代表商业替代；
- 把单次中标、装机或发货直接解释为活跃使用或收入兑现；
- 不同产品类别数据的无口径合并；
- 未经验证的市场份额、订单和渠道传闻。

### Geography And Time Horizon

- 中国监管、医院采购和支付环境为主；
- 美国、欧洲、日本等只用于产品/监管/临床/服务机制对照；
- 观察窗口：2022-2030；商业化 cohort 至少跟踪安装后 12-24 个月。

### Known Unknowns

- 医院层面的安装、开机、检查/手术量和维护数据公开性有限；
- 注册、招标、采购、安装和收入数据常分散在不同口径；
- 医生培训、workflow friction 和售后质量缺少统一量化；
- 同类产品在不同适应证和科室的替代难度差异大。

### Stop Conditions

- 无法建立同一 cohort 的 approval→tender→installation→active use 链；
- 只有供应商自述，没有监管、医院、临床或采购侧交叉验证；
- 无法区分 installed base 与 active installed base；
- 无法按产品类别、医院层级或适应证分层；
- 连续两个采集循环没有新增独立证据链。

## 2. Router Review

建议人工覆盖：

```text
primary_method: lifecycle
secondary_methods:
  - regulation
  - complex_system
  - commercialization
  - constraint_analysis
manual_override: true
override_reason: R2A Router 未表达商业化漏斗与跨阶段约束分析。
```

必需模块：lifecycle model、regulatory/clinical evidence model、hospital adoption model、service/ecosystem model、commercial funnel、constraint analysis、causal model、validation、invalidation。

## 3. Lifecycle Model Draft

```text
need definition / product design
→ engineering verification
→ preclinical / clinical evidence
→ registration submission and review
→ approval and listing eligibility
→ hospital budget and access
→ tender / procurement / contract
→ delivery, installation and acceptance
→ physician and staff training
→ workflow integration and active use
→ maintenance / uptime / software / consumables
→ recurring utilization and revenue
→ replacement / expansion / discontinuation
```

关键接口：

- regulator ↔ manufacturer evidence package；
- hospital administration ↔ department need and budget；
- procurement ↔ technical specification and tender；
- physician/team ↔ workflow and learning curve；
- service network ↔ uptime and response；
- installed equipment ↔ active usage and recurring economics。

### Planned Model And Causal IDs

| ID | Type | Meaning |
|---|---|---|
| `industry_node:high_end_medical_device_industry_bottleneck:technical_clinical_value` | industry model node | 技术性能、临床价值和 workflow fit |
| `industry_node:high_end_medical_device_industry_bottleneck:regulatory_evidence` | industry model node | 注册、临床证据和审评 |
| `industry_node:high_end_medical_device_industry_bottleneck:hospital_access_procurement` | industry model node | 预算、准入、招采和安装验收 |
| `industry_node:high_end_medical_device_industry_bottleneck:training_workflow` | industry model node | 培训、学习曲线和 active use |
| `industry_node:high_end_medical_device_industry_bottleneck:service_ecosystem` | industry model node | uptime、维护、耗材、软件和接口 |
| `industry_node:high_end_medical_device_industry_bottleneck:utilization_economics` | industry model node | 检查/手术量、TCO、支付、回款和持续收入 |
| `industry_node:high_end_medical_device_industry_bottleneck:manufacturing_field_supply` | industry model node | 制造一致性、交付和 field reliability |
| `causal_edge:high_end_medical_device_industry_bottleneck:r2b_value_to_evidence` | causal edge | 技术/临床价值 → 注册和采用证据 |
| `causal_edge:high_end_medical_device_industry_bottleneck:r2b_evidence_to_eligibility` | causal edge | 证据/审评 → 上市资格 |
| `causal_edge:high_end_medical_device_industry_bottleneck:r2b_eligibility_to_installation` | causal edge | 获批/准入/采购 → 安装验收 |
| `causal_edge:high_end_medical_device_industry_bottleneck:r2b_installation_to_active_use` | causal edge | 安装 → 培训/workflow → active use |
| `causal_edge:high_end_medical_device_industry_bottleneck:r2b_service_to_utilization` | causal edge | 服务/生态/可靠性 → uptime 和利用量 |
| `causal_edge:high_end_medical_device_industry_bottleneck:r2b_utilization_to_economics` | causal edge | 利用量 → 医院经济性与持续收入 |
| `causal_edge:high_end_medical_device_industry_bottleneck:r2b_proxy_to_false_inference` | causal edge | 注册/中标/装机代理指标 → 错误替代判断 |

Register 的 `target_node_or_process_id` 只使用上述 `industry_node`；`impact_path_edge_ids` 只使用上述 `causal_edge`。

## 4. Research Question Tree

`MED-Q00` Primary: 哪个生命周期阶段在当前产品/医院范围内构成真实商业化瓶颈？

### A. Technology And Clinical Value

- `MED-Q01` 产品性能、可靠性、安全性和 usability 是否达到临床工作流要求？
- `MED-Q02` 技术指标如何转化为 clinical outcome、效率、风险降低或总成本改善？
- `MED-Q03` 替代 incumbent workflow 是否需要改变医生、护士、技师或 IT 流程？

### B. Registration And Clinical Evidence

- `MED-Q04` 不同产品类别和适应证需要什么注册、临床和质量体系证据？
- `MED-Q05` 审评、补件、临床终点和 post-market requirement 如何影响上市时间？
- `MED-Q06` 获批是否只证明可销售，而不证明医院采用或支付？

### C. Hospital Access And Procurement

- `MED-Q07` 医院预算、设备配置许可、科室需求和院内准入如何形成采购前置条件？
- `MED-Q08` 招标评分、技术参数、价格、配套耗材和服务条款如何影响中标？
- `MED-Q09` 中标、合同、交付和安装验收之间有哪些取消或延迟风险？

### D. Physician Adoption And Workflow

- `MED-Q10` 医生学习曲线、培训时间和病例积累是否限制 active use？
- `MED-Q11` 关键意见领袖、科室协同、排班和临床路径如何影响渗透？
- `MED-Q12` 技术优势在真实 workflow 中是否被 setup time、interpretation burden 或操作复杂度抵消？

### E. Service, Maintenance And Ecosystem

- `MED-Q13` uptime、故障率、维修响应、备件和软件升级是否构成核心约束？
- `MED-Q14` 耗材、试剂、探头、配件或软件是否形成使用前置生态？
- `MED-Q15` 设备跨院区、科室或病例类型扩展需要哪些配套能力？

### F. Utilization And Economics

- `MED-Q16` approval、tender、installed、accepted、active、procedure volume 和 revenue 应如何定义？
- `MED-Q17` 医院的 capital budget、per-procedure economics、reimbursement 和 total cost of ownership 如何决定采用？
- `MED-Q18` 回款周期、耗材复购、service contract 和 utilization 怎样转化为持续收入？

### G. Competition And Substitution

- `MED-Q19` 国产产品存在与真正替代之间缺少哪一环？
- `MED-Q20` incumbent product 的 installed base、workflow、service network 和 clinician familiarity 构成多大 switching cost？
- `MED-Q21` 更低价格是否足以克服临床、培训、服务和生态差距？

### H. Counterfactual And Pseudo-bottleneck

- `MED-Q22` 若技术性能达到要求但 active use 低，核心约束应归因于注册、采购、医生还是服务？
- `MED-Q23` 哪些“国产替代卡点”只是注册证、招标或装机数量叙事？
- `MED-Q24` 若预算和支付改善但使用仍低，哪些隐性 workflow 约束仍存在？

### I. Validation And Invalidation

- `MED-Q25` 哪些 leading indicator 能区分即将商业化与闲置装机？
- `MED-Q26` 什么阈值说明某阶段瓶颈正在缓解？
- `MED-Q27` 哪些结果会否定“获批即可规模商业化”或“国产产品存在即替代”的命题？
- `MED-Q28` 不同证据多久过期，何时必须按新政策、招采或产品版本重审？

### Stable ID Disposition

`MED-Qxx` 是 Phase 1 alias，不直接作为 artifact ID。现有对象按下表保留 stable ID；其余问题使用 `question:high_end_medical_device_industry_bottleneck:r2b_qNN`。

| Alias | Stable ID | v0.2 disposition |
|---|---|---|
| MED-Q00 | `question:high_end_medical_device_industry_bottleneck:primary` | retained, text narrowed |
| MED-Q02 | `question:high_end_medical_device_industry_bottleneck:mechanism` | retained, expanded |
| MED-Q07 | `question:high_end_medical_device_industry_bottleneck:constraint` | retained, expanded |
| MED-Q17 | `question:high_end_medical_device_industry_bottleneck:economics` | retained, expanded |
| MED-Q22 | `question:high_end_medical_device_industry_bottleneck:counterfactual` | retained, expanded |
| MED-Q25 | `question:high_end_medical_device_industry_bottleneck:validation` | retained, expanded |

Existing primary and counter claim IDs are retained. The seven generic R2A requirements are preserved with `lifecycle_status=superseded`; MED-ER01, MED-ER02, MED-ER05, MED-ER14, MED-ER17, MED-ER20 and MED-ER19 respectively record them in `supersedes_requirement_id`. Existing Search Plans become `status=superseded` rather than disappearing.

其余 Phase 1 alias 在实现时采用固定映射，不允许 loader 猜测：

```text
MED-BHnn → bottleneck_hypothesis:high_end_medical_device_industry_bottleneck:r2b_bhnn
MED-ERnn → requirement:high_end_medical_device_industry_bottleneck:r2b_ernn
MED-Mnn  → validation_metric:high_end_medical_device_industry_bottleneck:r2b_mnn
MED-Inn  → invalidation_condition:high_end_medical_device_industry_bottleneck:r2b_inn
MED-CL-BHnn-S/C → claim:high_end_medical_device_industry_bottleneck:r2b_bhnn_supporting/counter
```

表格中的 single target alias 必须在 artifact 中解析成上述 exact `target_type + target_id`。每个 BH-targeted ER 同时要求独立的 supporting query 与 counter query；没有反方结果时记录已搜索范围，不能把“未找到”当作支持。

## 5. Bottleneck Hypothesis Register

| ID | Candidate bottleneck | Type | Mechanism | Counter explanation | Initial status |
|---|---|---|---|---|---|
| `MED-BH01` | 技术与临床价值不足 | technical | 性能、安全、可靠性或 workflow value 未达到采用阈值 | 商业化低可能由预算/采购而非技术造成 | proposed |
| `MED-BH02` | 注册与临床证据 | regulatory | 证据要求、补件和审评周期延迟可销售状态 | 获批后仍低使用说明注册不是核心长期约束 | proposed |
| `MED-BH03` | 医院预算、准入和采购 | economic | capital budget、配置、院内论证和招标延迟安装 | 已中标未使用说明采购不是最终约束 | proposed |
| `MED-BH04` | 医生培训与 workflow adoption | software_ecosystem | 学习曲线、流程变化和病例积累限制 active use | 强临床优势和简化培训可能快速消除摩擦 | proposed |
| `MED-BH05` | 售后维护、备件与 uptime | supply_chain | 故障、响应和维护网络降低可用时间和信任 | 产品可靠性提高或第三方服务可缓解 | proposed |
| `MED-BH06` | 耗材、软件与配套生态 | software_ecosystem | 缺少耗材、接口、软件或院内集成限制持续使用 | 开放标准或一次性设备模式降低生态依赖 | proposed |
| `MED-BH07` | active utilization 转化 | system | 中标/装机未形成真实检查或手术量 | cohort 尚在 ramp，低使用可能只是时滞 | proposed |
| `MED-BH08` | 支付、全生命周期经济性与回款 | economic | reimbursement、per-case economics、TCO 或回款压制采购和使用 | 临床刚需或显著效率提升可降低价格敏感度 | proposed |
| `MED-BH09` | 制造质量与稳定供应 | process | 质量一致性、交付、耗材供应或 field reliability 限制规模化 | 低商业化也可能主要由渠道和医院采用造成 | proposed |
| `MED-BH10` | “获批/装机即国产替代”伪卡点 | short_term_supply_demand | 统计口径把注册、中标或安装误当 active substitution | 若 utilization、procedure 和 recurring revenue 同步则叙事可能成立 | proposed |

### Register Field Draft

以下 ID 均是 Phase 1 planned ID；`research_version:high_end_medical_device_industry_bottleneck:0.2.0` 尚未创建。

| ID | Target / scope | Affected parameter and impact path | Severity / duration hypothesis | Substitution / mitigation | Planned links |
|---|---|---|---|---|---|
| MED-BH01 | `industry_node:high_end_medical_device_industry_bottleneck:technical_clinical_value`; product class/indication/workflow | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_value_to_evidence` | high if clinical/workflow threshold unmet; until redesign/evidence | workflow redesign; product iteration; alternate modality | claims `MED-CL-BH01-S/C`; ER07; metric `MED-M01`; invalidation `MED-I01` |
| MED-BH02 | `industry_node:high_end_medical_device_industry_bottleneck:regulatory_evidence`; product/version path | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_evidence_to_eligibility` | high pre-approval; may cease after approval | alternate indication/path; additional evidence | claims `MED-CL-BH02-S/C`; ER08; metric `MED-M02`; invalidation `MED-I02` |
| MED-BH03 | `industry_node:high_end_medical_device_industry_bottleneck:hospital_access_procurement`; tier/geography/cohort | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_eligibility_to_installation` | medium-high; annual budget/procurement cycle | lease/service model; budget reallocation; procurement change | claims `MED-CL-BH03-S/C`; ER09; metrics `MED-M03/M04`; invalidation `MED-I03` |
| MED-BH04 | `industry_node:high_end_medical_device_industry_bottleneck:training_workflow`; defined procedure/team | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_installation_to_active_use` | medium-high; 6-24 months after installation | simplified workflow; standard training; proctoring | claims `MED-CL-BH04-S/C`; ER10; metrics `MED-M05/M06`; invalidation `MED-I04` |
| MED-BH05 | `industry_node:high_end_medical_device_industry_bottleneck:service_ecosystem`; installed cohort | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_service_to_utilization` | medium; continuous after installation | reliability improvement; regional parts/service | claims `MED-CL-BH05-S/C`; ER11; metric `MED-M07`; invalidation `MED-I05` |
| MED-BH06 | `industry_node:high_end_medical_device_industry_bottleneck:service_ecosystem`; product/version | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_service_to_utilization` → `causal_edge:high_end_medical_device_industry_bottleneck:r2b_utilization_to_economics` | medium; ecosystem dependent | open interface; alternative consumable; bundled service | claims `MED-CL-BH06-S/C`; ER12; metric `MED-M08`; invalidation `MED-I06` |
| MED-BH07 | `industry_node:high_end_medical_device_industry_bottleneck:training_workflow`; accepted installation cohort | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_installation_to_active_use` → `causal_edge:high_end_medical_device_industry_bottleneck:r2b_utilization_to_economics` | high if conversion remains low after 12m | time-based ramp; department support | claims `MED-CL-BH07-S/C`; ER13; metrics `MED-M04/M06`; invalidation `MED-I07` |
| MED-BH08 | `industry_node:high_end_medical_device_industry_bottleneck:utilization_economics`; hospital/payment cohort | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_utilization_to_economics` | high where TCO/payment adverse; policy-cycle dependent | reimbursement change; efficiency gain; payment redesign | claims `MED-CL-BH08-S/C`; ER14; metrics `MED-M09/M10`; invalidation `MED-I08` |
| MED-BH09 | `industry_node:high_end_medical_device_industry_bottleneck:manufacturing_field_supply`; product/lot/cohort | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_service_to_utilization` | medium; until quality system and supply mature | process control; dual supply; corrective action | claims `MED-CL-BH09-S/C`; ER15; metrics `MED-M07/M11`; invalidation `MED-I09` |
| MED-BH10 | `industry_node:high_end_medical_device_industry_bottleneck:utilization_economics`; linked commercial cohort | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_proxy_to_false_inference` | narrative-level; while utilization data absent | linked utilization/procedure/revenue evidence | claims `MED-CL-BH10-S/C`; ER16; metrics `MED-M04/M06/M08`; invalidation `MED-I10` |

Common fields for all rows:

```text
scope: product class + indication + hospital tier/geography + cohort window
status: proposed
confidence: 0.20-0.35
lifecycle_status: active
created_in_version: planned research_version:high_end_medical_device_industry_bottleneck:0.2.0
```

Supporting and counter claim IDs must be separate `research_claim` objects. No row may advance until product stratification and counter-evidence coverage are explicit.

## 6. Evidence Requirement Matrix

每个 requirement 只有一个 `target_type + target_id`。`Plan` 是查询模板；Phase 2 仍为每个 ER 生成独立 Search Plan 和独立 counter query。

| ID | Single target | Required fact | Source classes | Primary / independence / freshness | Coverage and stop | Plan |
|---|---|---|---|---|---|---|
| `MED-ER01` | MED-Q00 | lifecycle stages and bottleneck framing | regulatory, hospital_primary, industry_association | yes; regulator + hospital/professional; 24m | each stage has entry/exit definition | SP-A |
| `MED-ER02` | MED-Q02 | technical parameter → clinical/workflow value mechanism | technical_standard, academic_research, hospital_primary | yes; engineering + user side; 36m | controlled and real-world scope distinguished | SP-B |
| `MED-ER03` | MED-Q04 | registration class and required evidence | regulatory, clinical_registry | yes; regulator primary; current rule | product/indication/version explicit | SP-C |
| `MED-ER04` | MED-Q06 | approval boundary versus adoption/payment | regulatory, hospital_primary, procurement_record | yes; regulator + adopter; 24m | evidence demonstrates what approval does not prove | SP-C |
| `MED-ER05` | MED-Q07 | budget/access/procurement constraint mechanism | hospital_primary, procurement_record, regulatory | yes; 2 hospital tiers/regions; 18m | funnel stages and cancellation points defined | SP-D |
| `MED-ER06` | MED-Q16 | approval/tender/install/active/procedure/revenue definitions | regulatory, procurement_record, utilization_data | yes; linked definitions; 12m | no mixed denominator or cohort | SP-G |
| `MED-ER07` | MED-BH01 | performance/reliability/usability/clinical value threshold | technical_standard, academic_research, engineering_validation | yes; independent clinical/engineering; 36m | at least one real workflow outcome | SP-B |
| `MED-ER08` | MED-BH02 | evidence package, review timeline and delay mechanism | regulatory, clinical_registry, review_record | yes; regulator primary; current | no cross-category extrapolation | SP-C |
| `MED-ER09` | MED-BH03 | hospital budget/access/tender/install conversion | hospital_primary, procurement_record, utilization_data | yes; two independent hospital/procurement chains; 18m | single tender cannot establish constraint | SP-D |
| `MED-ER10` | MED-BH04 | training hours, case ramp and workflow friction | hospital_primary, academic_research, engineering_validation | yes; user-side mandatory; 24m | one quantified learning/utilization measure | SP-E |
| `MED-ER11` | MED-BH05 | uptime, failure, response and maintenance capacity | service_record, hospital_primary, quality_record | yes; user/service cross-check; 12m | service-site count alone fails | SP-F |
| `MED-ER12` | MED-BH06 | consumable/software/interface dependency and availability | product_document, hospital_primary, procurement_record | yes; product + user; 18m | mandatory/optional and version explicit | SP-F |
| `MED-ER13` | MED-BH07 | accepted installation → active utilization cohort conversion | hospital_primary, utilization_data, procurement_record | yes; linked cohort; 12m | absent cohort linkage stops substitution conclusion | SP-G |
| `MED-ER14` | MED-BH08 | reimbursement, TCO, per-case economics and collection | payment_policy, hospital_primary, financial_operating_data | yes; policy + operating economics; current/12m | hospital economics separate from supplier revenue | SP-H |
| `MED-ER15` | MED-BH09 | quality consistency, delivery and field reliability | quality_record, regulatory, supply_capacity | yes; regulatory/quality + user; 18m | nominal capacity cannot substitute for delivery quality | SP-F |
| `MED-ER16` | MED-BH10 | whether approval/tender/install predicts active substitution | procurement_record, utilization_data, financial_operating_data | yes; linked cohort; 12m | proxy-only evidence fails | SP-G |
| `MED-ER17` | MED-Q20 | incumbent switching cost and alternative workflow | hospital_primary, academic_research, industry_association | yes; user-side + independent; 24m | include failed/no-switch evidence | SP-E |
| `MED-ER18` | `causal_edge:high_end_medical_device_industry_bottleneck:r2b_installation_to_active_use` | installation→training/workflow→use causal bridge | hospital_primary, utilization_data, academic_research | yes; mechanism + time series; 12-24m | correlation-only evidence fails | SP-G |
| `MED-ER19` | existing primary claim | support, opposition, scope and alternative mechanism | all applicable classes | yes; 3 independent families; mixed | each BH has opposing search coverage | SP-I |
| `MED-ER20` | MED-Q25 | policy, procurement, utilization and quality freshness for validation | all applicable classes | conditional; class-specific limits | any stale blocking chain stops readiness | SP-I |

## 7. Source Acquisition Plan

| Plan | ER coverage | First priority | Supplement | Discovery-only bias / access failure |
|---|---|---|---|---|
| SP-A Lifecycle | ER01 | regulator lifecycle rules and hospital process documents | professional association workflow | generic articles only locate primary records |
| SP-B Clinical value | ER02, ER07 | peer-reviewed clinical/engineering evidence and hospital protocols | engineering conference and real-world studies | vendor claims are conflicted; no independent evidence keeps proposed |
| SP-C Regulation | ER03-04, ER08 | formal rules, review requirements, registry and review records | specialist regulatory interpretation | preserve rule version/effective date; no cross-class inference |
| SP-D Access/procurement | ER05, ER09 | hospital access, budget, tender and acceptance records | procurement database and independent field research | a tender notice does not prove installation or use |
| SP-E Adoption/switching | ER10, ER17 | training, case-ramp, workflow and failed-adoption records | interview artifact and academic study | KOL opinion alone cannot quantify adoption |
| SP-F Service/quality/ecosystem | ER11-12, ER15 | quality/recall/service records and formal product/interface specs | hospital feedback and professional quality research | site count/capacity/marketing only sets a lead |
| SP-G Funnel/utilization | ER06, ER13, ER16, ER18 | linked procurement, acceptance and utilization cohorts | hospital operational series | preserve cohort/denominator; proxy-only data fails |
| SP-H Economics | ER14 | payment policy, hospital TCO/per-case economics and collection records | HTA and market data | supplier revenue cannot prove hospital ROI |
| SP-I Counter/freshness | ER19-20 | opposing primary/user evidence and recurring current series | independent professional analysis | absence of opposition is not support; record searched scope |

统一保存 URL、publisher、publish/access date、product class、indication、hospital scope、locator、content hash、provenance 和 source role。转载或同源材料合并为一条证据链。

## 8. Validation Metrics Draft

| ID | Metric | Unit | Baseline plan | Confirmation direction | Warning concept |
|---|---|---|---|---|---|
| `MED-M01` | clinical/workflow value versus incumbent | outcome/time/cost index | product/indication comparator | material benefit supports BH01 resolution | lab metric without workflow value is insufficient |
| `MED-M02` | submission-to-approval cycle and supplement burden | months/count | product class/version | long variable cycle supports BH02 | cycle normalization weakens it |
| `MED-M03` | approval-to-tender conversion | %/months | approved product cohort | higher/faster weakens BH03 | approval high but tender low locates downstream constraint |
| `MED-M04` | tender-to-accepted-install and active conversion | %/months | linked tender cohort | stable conversion supports execution | cancellation/idle installation supports BH03/BH07 |
| `MED-M05` | training-to-independent-use time | weeks/cases | clinician cohort | shorter time weakens BH04 | long/variable ramp supports it |
| `MED-M06` | procedure/exam volume per active unit | count/time | product/hospital cohort | sustained ramp supports commercialization | flat use supports workflow/economic constraint |
| `MED-M07` | uptime, failure and service response | %/count/hours | installed cohort | high uptime/fast response weakens BH05/BH09 | repeated downtime supports service/quality constraint |
| `MED-M08` | consumable/software/service renewal | %/currency | active cohort | recurring use supports ecosystem transition | low renewal questions active adoption |
| `MED-M09` | hospital TCO/per-case economics | currency/case | incumbent comparator | improvement weakens BH08 | adverse economics supports BH08 |
| `MED-M10` | cash collection cycle | days | contract cohort | stable collection supports commercial completion | deterioration separates accounting revenue from cash |
| `MED-M11` | acceptance/field quality failure rate | %/count | product lot/cohort | low stable rate weakens BH09 | repeated field correction supports it |

### Invalidation Condition Draft

| ID | Target | Observable test | Threshold / persistence | Recovery condition |
|---|---|---|---|---|
| `MED-I01` | BH01 | independent clinical/workflow outcome meets adoption threshold | clinical threshold plus workflow benefit in >=2 centers | material regression or safety/reliability signal |
| `MED-I02` | BH02 | review becomes predictable and ceases to delay eligible supply | cycle within statutory/peer range for 2 cohorts | renewed supplement burden or delay |
| `MED-I03` | BH03 | approved products convert through procurement/install | >=70% cohort conversion within defined budget cycle | conversion <40% for 2 cohorts |
| `MED-I04` | BH04 | clinicians reach independent use rapidly and consistently | target competency within preset cases/time in >=2 centers | ramp exceeds threshold in 2 cohorts |
| `MED-I05` | BH05 | uptime/service meets hospital SLA | uptime >=98% and response within SLA for 12m | repeated SLA breach for 2 quarters |
| `MED-I06` | BH06 | ecosystem components no longer constrain cases | required inputs available for >=95% scheduled cases for 12m | availability <90% for 2 quarters |
| `MED-I07` | BH07 | accepted units become active and ramp utilization | >=70% active at 12m with rising procedure volume | active conversion <40% at 12m |
| `MED-I08` | BH08 | economics/payment no longer blocks use or collection | TCO meets comparator and collection stable for 2 cohorts | TCO disadvantage or collection deterioration persists 2 quarters |
| `MED-I09` | BH09 | field quality and delivery stabilize | acceptance failure below class threshold for 12m | repeated corrective action or supply interruption |
| `MED-I10` | BH10 | proxy metrics reliably predict utilization/revenue | stable proxy-to-outcome conversion for 2 linked cohorts | proxy/outcome divergence recurs |

## 9. Phase 2 Entry Condition

Phase 2 只能在以下条件满足后开始：

- 用户接受跨产品商业化漏斗，但要求所有证据按产品类别分层；
- 用户接受 10 个 candidate hypothesis 均为待验证；
- schema extension 获批；
- AI PCB 第一轮 coverage review 已完成，避免两线同时进入大规模抓取；
- 不使用 V1 company mapping 或公司列表作为来源发现起点。
