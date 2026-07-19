# R2B Pilot Design — AI Compute PCB Value Migration

更新日期：2026-07-20

状态：Phase 1 research design。所有瓶颈均为待验证 hypothesis，不是产业结论。

## 1. Scope Confirmation

### Primary Question

AI 服务器与 GPU 集群架构升级，如何通过板卡结构、信号速率、材料和制造约束改变 PCB 及上游材料的单位内容、有效供给与价值分配？

### Included Scope

- AI server/node 内的 server board、accelerator/baseboard、NIC/DPU、power/control board；
- rack 内 scale-up 与 scale-out switch board、backplane/midplane/cable-board boundary；
- 800G、1.6T 及后续高速互连对电气 PCB 的影响；
- PCB 面积、层数、材料等级、线宽线距、孔结构、背钻、HDI、多次压合、表面处理、检测和良率；
- 覆铜板、玻纤布、铜箔、树脂、PCB 制造与关键设备；
- 名义产能、认证产能、稳定良率产能和可交付有效产能；
- 按 server、rack、accelerator 和 network port 归一化的 quantity/content/ASP/value migration；
- CPO、silicon photonics、board-level optical interconnect、cable/backplane redesign 等替代路线。

### Excluded Scope

- 公司名单、供应商排名、公司能力评分；
- 订单传闻、股票评级、估值、目标价、watchlist 或策略；
- GPU、交换芯片或光模块本体的公司价值研究；
- 尚未形成公开工程证据的未来产品传闻；
- 把总 AI server 出货增长直接当作 PCB 单位价值迁移。

### Geography And Time Horizon

- 全球架构、标准与工程证据；
- 中国、北美、亚洲 PCB/材料供给口径；
- 观察窗口：2023-2030，重点比较连续两个已出货架构代际；
- 任何预测必须注明 base date 和 scenario。

### Assumptions

- 至少能获得两代可比较的系统/板卡结构或可靠工程拆解；
- 名义产能与高规格有效产能可以通过良率、认证、产品 mix 或交付记录交叉验证；
- 价格、ASP 和成本口径可以区分产品规格变化与短期涨价。

### Known Unknowns

- 闭源平台的完整 rack BOM、板层和材料信息可能不可得；
- 下一代 scale-up topology 与 optical/electrical boundary 仍在变化；
- 高端板良率、客户认证产能和真实切换成本缺少统一公开口径；
- 同一“高速材料”等级在不同供应商命名中不可直接比较。

### Stop Conditions

- 无法获得两代可比、已出货架构的板卡或 BOM 证据；
- 核心瓶颈仅由相互转载的单一来源支撑；
- 无法区分产品 mix、数量增长和单位价值；
- 关键供给判断无法区分名义产能与有效产能；
- 连续两个采集循环没有新增独立证据链。

## 2. Router Review

建议人工覆盖：

```text
primary_method: system_architecture
secondary_methods:
  - manufacturing_process
  - constraint_analysis
  - infrastructure_economics
  - value_migration
manual_override: true
override_reason: 当前 Pilot 已有枚举支持 infrastructure_economics 但未选用；现有枚举尚未表达 constraint_analysis 和结构化 value_migration，因此补选前者并以必需模块记录后两者。
```

必需模块：architecture model、manufacturing model、capacity/yield model、qualification model、substitution model、causal model、value migration、validation、invalidation。

## 3. Industry Model Draft

### Architecture Nodes

```text
AI compute node
├── accelerator/baseboard
├── server/host board
├── NIC/DPU or fabric adapter
├── power/control boards
└── internal cable/connector boundary

AI rack / cluster network
├── scale-up switch board
├── scale-out switch board
├── backplane/midplane or cable replacement
├── optical module / CPO boundary
└── rack-level power and management boards
```

### Manufacturing Flow

```text
resin / copper foil / glass cloth
→ copper clad laminate
→ inner-layer imaging and etching
→ lamination / sequential lamination
→ drilling / laser drilling / via formation
→ plating
→ outer-layer imaging
→ backdrill / impedance / surface finish
→ electrical and signal-integrity testing
→ customer qualification
→ stable-volume production
```

### Key Parameters

- board count and area per server/rack/accelerator;
- layer count and sequential lamination count;
- line width/spacing, via density, aspect ratio and backdrill depth tolerance;
- insertion loss, dielectric constant/loss, copper roughness and material consistency;
- first-pass yield, final yield and rework/scrap rate;
- qualification cycle, product generation life and change-control burden;
- nominal capacity, qualified capacity and effective shipped capacity;
- ASP, material cost, processing cost, capex intensity and working capital.

### Planned Model And Causal IDs

| ID | Type | Meaning |
|---|---|---|
| `industry_node:ai_compute_pcb_industry_bottleneck:compute_node_boards` | industry model node | server/baseboard/NIC/power boards |
| `industry_node:ai_compute_pcb_industry_bottleneck:rack_network_boards` | industry model node | scale-up/scale-out switch and backplane boundary |
| `industry_node:ai_compute_pcb_industry_bottleneck:pcb_process` | industry model node | high-layer/high-speed PCB manufacturing flow |
| `industry_node:ai_compute_pcb_industry_bottleneck:material_system` | industry model node | CCL/glass/foil/resin material system |
| `industry_node:ai_compute_pcb_industry_bottleneck:equipment_test` | industry model node | drilling/lamination/test equipment capability |
| `industry_node:ai_compute_pcb_industry_bottleneck:qualification` | industry model node | platform/customer qualification |
| `industry_node:ai_compute_pcb_industry_bottleneck:optical_boundary` | industry model node | electrical/optical/integration substitution boundary |
| `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_architecture_to_content` | causal edge | architecture → board/content parameters |
| `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_content_to_process` | causal edge | content/specification → process complexity |
| `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_process_to_effective_capacity` | causal edge | process/yield/qualification → effective capacity |
| `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_constraint_to_value` | causal edge | constraint + content → price/cost/value migration |
| `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_substitution_to_content` | causal edge | optical/integration substitution → content relocation |

Register `target_node_or_process_id` uses an `industry_node` above. `impact_path_edge_ids` uses only the listed `causal_edge` IDs.

## 4. Research Question Tree

`PCB-Q00` Primary: AI compute architecture upgrade 是否形成可持续、可归一化的 PCB 与材料价值迁移？

### A. System Architecture

- `PCB-Q01` AI server 与 general-purpose server 的 board topology、board count、board area 和 accelerator/network attachment 有何差异？
- `PCB-Q02` scale-up 与 scale-out 的 GPU、switch ASIC、NIC/DPU、accelerator card 和 backplane 数量如何随架构代际变化？
- `PCB-Q03` 新增 PCB content 主要发生在 compute node、rack switch 还是 data-center network？
- `PCB-Q04` 不同 normalization denominator（server、rack、accelerator、port、aggregate bandwidth）会如何改变结论？

### B. Signal And Material Mechanism

- `PCB-Q05` 800G、1.6T 与更高速率怎样改变 channel loss budget、trace length、layer stack-up 和材料等级？
- `PCB-Q06` 低损耗树脂、玻纤布、铜箔粗糙度和 CCL consistency 中，哪些参数真正影响量产性能？
- `PCB-Q07` 更高频率是否必然增加 PCB 层数，还是可由 topology、connector、cable 或 optical boundary 改变？

### C. Manufacturing Process

- `PCB-Q08` 高层数、HDI、背钻、多次压合、细线和高 aspect-ratio via 如何影响工序、cycle time 和 yield？
- `PCB-Q09` 哪些关键设备或检测能力限制高规格板，而不是普通名义产能？
- `PCB-Q10` 材料批次一致性和 process window 如何影响稳定交付？

### D. Supply And Effective Capacity

- `PCB-Q11` 名义面积产能、可生产高端板产能、已认证产能和稳定良率产能分别是多少？
- `PCB-Q12` 扩产从设备到位到 qualified effective capacity 需要多久？
- `PCB-Q13` 客户认证、change control 和产品迭代会不会使旧产能无法快速替代？
- `PCB-Q14` 同一扩产公告中，多少产能可用于目标 layer/material/process mix？

### E. Demand And Economics

- `PCB-Q15` 单位价值增加分别来自 quantity、area、layers、material grade、process complexity、yield loss 和 ASP 的多少？
- `PCB-Q16` 规格增值是否覆盖材料成本、scrap、capex depreciation、qualification cost 和价格竞争？
- `PCB-Q17` 短期涨价与长期结构性 ASP/mix 提升如何区分？

### F. Competition And Substitution

- `PCB-Q18` 供应商集中来自技术、认证、客户关系、设备、良率还是暂时产能错配？
- `PCB-Q19` 新进入者或既有普通产能升级的真实时间和失败模式是什么？
- `PCB-Q20` CPO、silicon photonics、board-level optics、cable replacement、advanced packaging 或 board simplification 会减少哪些 PCB content？

### G. Counterfactual And Pseudo-bottleneck

- `PCB-Q21` 若 demand growth slower、architecture integration higher 或 capacity ramp faster，哪些“卡点”会消失？
- `PCB-Q22` 哪些市场叙事只证明需求增长，没有证明约束或价值迁移？
- `PCB-Q23` 若材料供应充足但 yield 仍低，瓶颈应归因于材料、工艺还是 qualification？

### H. Validation And Invalidation

- `PCB-Q24` 哪些指标能最早发现有效产能、良率或认证瓶颈缓解？
- `PCB-Q25` 哪些阈值能否定单位 PCB content 或长期 ASP 提升？
- `PCB-Q26` 证据多久过期，何时必须重新审查架构与材料结论？

### Stable ID Disposition

`PCB-Qxx` 是 Phase 1 alias，不直接作为 artifact ID。现有对象按下表保留 stable ID；其余问题使用 `question:ai_compute_pcb_industry_bottleneck:r2b_qNN`。

| Alias | Stable ID | v0.2 disposition |
|---|---|---|
| PCB-Q00 | `question:ai_compute_pcb_industry_bottleneck:primary` | retained, text narrowed |
| PCB-Q02 | `question:ai_compute_pcb_industry_bottleneck:mechanism` | retained, expanded |
| PCB-Q11 | `question:ai_compute_pcb_industry_bottleneck:constraint` | retained, expanded |
| PCB-Q16 | `question:ai_compute_pcb_industry_bottleneck:economics` | retained, expanded |
| PCB-Q20 | `question:ai_compute_pcb_industry_bottleneck:counterfactual` | retained, expanded |
| PCB-Q24 | `question:ai_compute_pcb_industry_bottleneck:validation` | retained, expanded |

Existing primary and counter claim IDs are retained. The seven generic R2A requirements are preserved with `lifecycle_status=superseded`; ER01, ER03, ER08, ER15, ER17, ER20 and ER19 respectively record them in `supersedes_requirement_id`. Existing Search Plans become `status=superseded` rather than disappearing.

其余 Phase 1 alias 在实现时采用固定映射，不允许 loader 猜测：

```text
PCB-BHnn → bottleneck_hypothesis:ai_compute_pcb_industry_bottleneck:r2b_bhnn
PCB-ERnn → requirement:ai_compute_pcb_industry_bottleneck:r2b_ernn
PCB-Mnn  → validation_metric:ai_compute_pcb_industry_bottleneck:r2b_mnn
PCB-Inn  → invalidation_condition:ai_compute_pcb_industry_bottleneck:r2b_inn
PCB-CL-BHnn-S/C → claim:ai_compute_pcb_industry_bottleneck:r2b_bhnn_supporting/counter
```

表格中的 single target alias 必须在 artifact 中解析成上述 exact `target_type + target_id`。每个 BH-targeted ER 同时要求独立的 supporting query 与 counter query；没有反方结果时记录已搜索范围，不能把“未找到”当作支持。

## 5. Bottleneck Hypothesis Register

| ID | Candidate bottleneck | Type | Mechanism | Counter explanation | Initial status |
|---|---|---|---|---|---|
| `PCB-BH01` | 高层高速 PCB 有效产能 | effective_capacity | 工艺复杂度降低稳定良率，认证进一步缩小可交付产能 | 扩产和产品 mix 调整可能快速释放供给 | proposed |
| `PCB-BH02` | 多次压合、背钻、HDI 与细线工艺窗口 | process | 多工序叠加提高缺陷概率和 cycle time | 设计优化、设备升级和 learning curve 可缓解 | proposed |
| `PCB-BH03` | 低损耗 CCL 与材料一致性 | material | loss、Dk/Df、铜粗糙度和批次一致性限制高速量产 | channel shortening、equalization 或替代材料可降低要求 | proposed |
| `PCB-BH04` | 高规格玻纤布、铜箔或树脂供给 | supply_chain | 上游专用规格认证和扩产周期限制有效供给 | 名义供给可能充足，真实瓶颈在 PCB yield | proposed |
| `PCB-BH05` | 客户 qualification 与 change control | qualification | 平台验证周期和变更成本使供给集中 | 架构快速迭代也可能缩短旧认证优势 | proposed |
| `PCB-BH06` | 高速测试、钻孔、压合或检测设备 | equipment | 特定设备精度、throughput 或测试能力限制扩产 | 设备并非稀缺，限制可能是 operator/process integration | proposed |
| `PCB-BH07` | 架构代际带来的短期供需错配 | short_term_supply_demand | demand step-up 快于 qualified capacity ramp | 不构成长期技术壁垒，扩产后价格回落 | proposed |
| `PCB-BH08` | 电气 PCB content 被 optical/integration 替代 | system | CPO、board-level optics、cable 或 advanced packaging 缩短 electrical trace | 光电边界前移仍可能提高其他高端板 complexity | proposed |

### Register Field Draft

以下 ID 均是 Phase 1 planned ID；`research_version:ai_compute_pcb_industry_bottleneck:0.2.0` 尚未创建。

| ID | Target / scope | Affected parameter and impact path | Severity / duration hypothesis | Substitution / mitigation | Planned links |
|---|---|---|---|---|---|
| PCB-BH01 | `industry_node:ai_compute_pcb_industry_bottleneck:pcb_process`; shipped AI boards | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_process_to_effective_capacity` → `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_constraint_to_value` | high for 2-6 quarters after architecture ramp | multi-source qualification; yield learning; qualified expansion | claims `PCB-CL-BH01-S/C`; ER08; metrics `PCB-M01/M02`; invalidation `PCB-I01` |
| PCB-BH02 | `industry_node:ai_compute_pcb_industry_bottleneck:pcb_process`; complex process window | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_content_to_process` → `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_process_to_effective_capacity` | medium-high; one to three product generations | design rule relaxation; process control; equipment upgrade | claims `PCB-CL-BH02-S/C`; ER09; metric `PCB-M03`; invalidation `PCB-I02` |
| PCB-BH03 | `industry_node:ai_compute_pcb_industry_bottleneck:material_system`; defined speed/channel | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_content_to_process` | medium; architecture and grade dependent | shorter channel; equalization; alternative material | claims `PCB-CL-BH03-S/C`; ER10; metric `PCB-M04`; invalidation `PCB-I03` |
| PCB-BH04 | `industry_node:ai_compute_pcb_industry_bottleneck:material_system`; grade-specific supply | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_process_to_effective_capacity` | medium; expected 2-8 quarters if real | upstream expansion; alternate qualification | claims `PCB-CL-BH04-S/C`; ER11; metrics `PCB-M04/M05`; invalidation `PCB-I04` |
| PCB-BH05 | `industry_node:ai_compute_pcb_industry_bottleneck:qualification`; platform/customer scope | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_process_to_effective_capacity` | high during stable generation | multi-source design; standardized stack-up | claims `PCB-CL-BH05-S/C`; ER12; metric `PCB-M06`; invalidation `PCB-I05` |
| PCB-BH06 | `industry_node:ai_compute_pcb_industry_bottleneck:equipment_test`; target processes | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_process_to_effective_capacity` | medium; lead time plus qualification | parallel equipment; test/process improvement | claims `PCB-CL-BH06-S/C`; ER13; metric `PCB-M07`; invalidation `PCB-I06` |
| PCB-BH07 | `industry_node:ai_compute_pcb_industry_bottleneck:pcb_process`; launch cohort | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_constraint_to_value` | high but normally <=6 quarters | ramp completion; demand normalization | claims `PCB-CL-BH07-S/C`; ER16; metrics `PCB-M02/M08`; invalidation `PCB-I07` |
| PCB-BH08 | `industry_node:ai_compute_pcb_industry_bottleneck:optical_boundary`; target architecture | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_substitution_to_content` | uncertain; >=2 generations | substitution path itself | claims `PCB-CL-BH08-S/C`; ER17; metric `PCB-M09`; invalidation `PCB-I08` |

Common fields for all rows:

```text
status: proposed
confidence: 0.20-0.35
lifecycle_status: active
created_in_version: planned research_version:ai_compute_pcb_industry_bottleneck:0.2.0
```

The planned supporting and counter claim IDs must be created as separate `research_claim` objects. No row may change status from `proposed` until its linked requirement and counter-evidence coverage exist.

## 6. Evidence Requirement Matrix

每个 requirement 只有一个 `target_type + target_id`。表中的 `Plan` 是查询模板；Phase 2 仍为每个 ER 生成独立 Search Plan 和独立 counter query。

| ID | Single target | Required fact | Source classes | Primary / independence / freshness | Coverage and stop | Plan |
|---|---|---|---|---|---|---|
| `PCB-ER01` | PCB-Q00 | overall architecture→PCB value mechanism | customer_primary, engineering_validation, independent_secondary | yes; 2 families; 18m | two shipped generations or stop broad conclusion | SP-A |
| `PCB-ER02` | PCB-Q01 | server vs general server board topology | customer_primary, engineering_validation | yes; 2 platform families; 18m | board count/area for both classes | SP-A |
| `PCB-ER03` | PCB-Q02 | accelerator/switch/NIC/backplane count by generation | customer_primary, engineering_validation | yes; 2 generations; 18m | comparable shipped configurations | SP-A |
| `PCB-ER04` | PCB-Q03 | compute-node vs rack/network content location | engineering_validation, market_data | yes; 2 families; 18m | server/rack/network bridge | SP-A |
| `PCB-ER05` | PCB-Q04 | denominator sensitivity | BOM, quantitative_demand, market_data | yes; independent reconciliation; 12m | server/rack/accelerator/port denominators | SP-E |
| `PCB-ER06` | PCB-Q05 | speed/channel-loss requirement | technical_standard, academic_research, engineering_validation | yes; standard + engineering; 36m | one standard and two engineering parameter sets | SP-B |
| `PCB-ER07` | PCB-Q06 | material parameter and consistency requirement | technical_standard, material_specification, engineering_validation | yes; upstream/downstream; 24m | grade and channel scope mapped | SP-B |
| `PCB-ER08` | PCB-BH01 | nominal vs qualified/effective PCB capacity | supply_capacity, customer_primary, market_data | yes; 2 capacity chains; 12m | product mix + yield/qualification proxy | SP-D |
| `PCB-ER09` | PCB-BH02 | process-window effect on yield/cycle | manufacturing_process, engineering_validation, equipment_specification | yes; 3 families; 24m | volume/engineering evidence required | SP-C |
| `PCB-ER10` | PCB-BH03 | low-loss CCL consistency mechanism | technical_standard, material_specification, engineering_validation | yes; 2 families; 24m | performance + volume consistency | SP-B |
| `PCB-ER11` | PCB-BH04 | grade-specific upstream effective supply | supply_capacity, material_specification, customer_primary | yes; two supply-chain levels; 12m | qualification/product grade required | SP-D |
| `PCB-ER12` | PCB-BH05 | qualification cycle and switching cost | customer_primary, engineering_validation, company_primary | yes; customer-side mandatory; 24m | one customer and one supply-side chain | SP-D |
| `PCB-ER13` | PCB-BH06 | equipment precision/throughput constraint | equipment_specification, manufacturing_process, engineering_validation | yes; 2 equipment/process families; 24m | distinguish equipment from integration bottleneck | SP-C |
| `PCB-ER14` | PCB-Q15 | quantity/area/layer/material/process/ASP bridge | BOM, cost_data, market_data | yes; 2 quantitative chains; 12m | components add to normalized total | SP-E |
| `PCB-ER15` | PCB-Q16 | economics after yield/capex/qualification | cost_data, market_data, independent_secondary | yes; independent reconciliation; 12m | no conclusion without cost bridge | SP-E |
| `PCB-ER16` | PCB-BH07 | demand step-up vs qualified supply ramp | quantitative_demand, shipment_data, supply_capacity | yes; demand/supply independent; 9m | four quarters; announcements alone fail | SP-D |
| `PCB-ER17` | PCB-BH08 | optical/integration substitution | technical_standard, customer_primary, engineering_validation | yes; 2 architecture families; 18m | identify removed and added complexity | SP-F |
| `PCB-ER18` | `causal_edge:ai_compute_pcb_industry_bottleneck:r2b_constraint_to_value` | constraint→price/content/value causal bridge | engineering_validation, market_data, cost_data | yes; mechanism + quantification; 12m | correlation-only evidence fails | SP-E |
| `PCB-ER19` | existing primary claim | overall support, opposition and boundary | all applicable classes | yes; 3 independent families; mixed | all BH requirements reviewed; unresolved conflict visible | SP-G |
| `PCB-ER20` | PCB-Q24 | freshness and coverage audit for bottleneck validation | all applicable classes | conditional; per-class limits | any stale blocking chain stops readiness | SP-G |

## 7. Source Acquisition Plan

| Plan | ER coverage | First priority | Supplement | Discovery-only bias / access failure |
|---|---|---|---|---|
| SP-A Architecture | ER01-04 | shipped platform/system/board primary documents | teardown and professional engineering analysis | news/forum only locates documents; missing BOM stays a gap |
| SP-B Standard/material | ER06-07, ER10 | standards and formal material specifications | academic measurement and SI conference material | marketing whitepaper is biased; preserve version/page/section |
| SP-C Process/equipment | ER09, ER13 | process validation and equipment capability documents | patents and professional manufacturing research | purchase/order is not a bottleneck; require process evidence |
| SP-D Capacity/qualification | ER08, ER11-12, ER16 | product-grade capacity, customer qualification and shipped supply | capacity database and supply-chain cross-check | nominal area/announcement only sets an upper bound |
| SP-E Quantification/economics | ER05, ER14-15, ER18 | BOM, price/cost series and denominator bridge | professional market data | preserve unit/currency/tax/date; forecast and actual separate |
| SP-F Substitution | ER17 | standards, shipped architecture and engineering validation | technical research | roadmap/demo is not adoption; record TRL and commercial state |
| SP-G Counter/freshness | ER19-20 | opposing primary/engineering evidence and recurring fresh series | independent professional analysis | absence of opposition is not support; record searched scope |

统一保存 URL、title、publisher、publish date、access date、document version、locator、content hash、provenance 和 source role。转载材料通过 source relationship 合并为一个证据链。

## 8. Validation Metrics Draft

| ID | Metric | Unit | Baseline plan | Confirmation direction | Warning concept |
|---|---|---|---|---|---|
| `PCB-M01` | normalized PCB value per accelerator | index/currency | two shipped generations | sustained increase after mix bridge | <=0 challenges broad value claim |
| `PCB-M02` | effective capacity utilization / lead time | % / weeks | qualified target-product capacity | persistently high/long supports BH01/BH07 | normalization signals easing |
| `PCB-M03` | target-product first-pass/final yield | % | comparable stack-up | low and slow ramp supports BH02 | stable high yield weakens it |
| `PCB-M04` | material loss/consistency acceptance | parameter/pass rate | grade/channel cohort | narrow window or failures support BH03 | broad qualification weakens it |
| `PCB-M05` | grade-specific material lead time/premium | weeks / % | exact grade | persistent premium supports BH04 | broad price normalization weakens it |
| `PCB-M06` | qualification cycle / approved sources | months / count | platform cohort | long cycle/few sources supports BH05 | faster multi-source approval weakens it |
| `PCB-M07` | equipment process capability / utilization | Cpk/% | target process | capability shortfall supports BH06 | adequate spare capability weakens it |
| `PCB-M08` | demand-to-qualified-supply gap | % / quarters | four-quarter series | temporary positive gap supports BH07 | sustained closure rejects structural shortage |
| `PCB-M09` | optical/electrical boundary adoption | % ports/systems | architecture cohort | adoption tests BH08 substitution | no commercial adoption keeps it proposed |

### Invalidation Condition Draft

| ID | Target | Observable test | Threshold / persistence | Recovery condition |
|---|---|---|---|---|
| `PCB-I01` | BH01 | effective supply catches demand without persistent lead time | gap <=0 for 2 quarters | gap >10% for 2 quarters |
| `PCB-I02` | BH02 | comparable complex boards reach mature yield | yield within 5pp of mature board for 2 quarters | gap >10pp |
| `PCB-I03` | BH03 | multiple qualified material systems meet channel/yield target | >=3 independent qualified systems | qualification falls below 2 |
| `PCB-I04` | BH04 | grade-specific supply/lead time normalizes | premium <5% and lead time normal for 2 quarters | premium >10% for 2 quarters |
| `PCB-I05` | BH05 | multi-source qualification becomes fast and repeatable | >=3 sources and cycle <6 months for 2 generations | sources <2 or cycle >12 months |
| `PCB-I06` | BH06 | equipment capacity exceeds qualified process demand | utilization <70% with capability pass for 2 quarters | utilization >90% or capability failure |
| `PCB-I07` | BH07 | launch mismatch ends | supply-demand gap <=0 for 2 quarters | positive gap resumes for 2 quarters |
| `PCB-I08` | BH08 | substitution does not reach commercial scope | adoption <5% across 2 generations | adoption >15% in target scope |

## 9. Phase 2 Entry Condition

Phase 2 只能在以下条件满足后开始：

- 用户确认 scope 和 Router override；
- 用户确认 8 个 hypothesis 均为候选，不代表结论；
- schema extension 方案获批；
- 每个 requirement 已映射到 Search Plan，不进行泛化网页搜集；
- High-End Medical Device 不与本 Pilot 并行抓取，先完成 AI PCB 的第一轮 coverage review。
