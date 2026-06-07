# Tech Chain Taxonomy Design

## Purpose

`tech-bottleneck-discovery` currently recognizes bottlenecks through a relatively generic hard-tech vocabulary: domestic substitution, self-reliance, core technology, patents, customer certification, and capacity. That works for many semiconductor equipment, materials, and industrial component cases, but it under-recognizes AI infrastructure chains where bottlenecks are expressed through generation transitions, supply allocation, yield, packaging, customer qualification, and delivery capacity.

This design adds a configurable `tech_chain_taxonomy` layer. The goal is not to tune the strategy for individual stocks. The goal is to describe technology supply chains and their bottleneck dimensions once, then use those chain definitions consistently across candidate gating, evidence quality review, miss audit, and historical replay.

## Scope

The first version covers twenty hard-tech bottleneck chains:

1. AI optical modules / optical communication
2. AI chips / compute accelerators
3. HBM / high-end memory
4. Advanced packaging
5. ABF / high-end package substrates
6. AI server PCB
7. MLCC / high-end passive components
8. Power management / power delivery
9. Liquid cooling / thermal management
10. Data center fiber / high-speed connectors
11. Semiconductor equipment
12. Lithography / EDA / semiconductor IP
13. Semiconductor materials
14. Power semiconductors
15. High-end sensors
16. Robotics core components
17. Industrial software / control systems
18. High-end magnetic and inductor materials
19. High-end ceramics / electronic materials
20. Power grid / energy infrastructure

The initial implementation should be configuration driven. Adding a chain should not require changing scoring logic.

## Chain Schema

Each chain definition contains:

- `chain_id`: stable machine key, such as `ai_optical_interconnect`.
- `display_name`: Chinese display name for reports.
- `chain_context_terms`: terms that identify the industry chain context.
- `product_exposure_terms`: terms that link revenue, products, or business lines to the chain.
- `bottleneck_dimensions`: named dimensions specific to the chain.
- `technical_execution_terms`: terms showing technical execution, yield, product generation, platform capability, or process barriers.
- `commercial_validation_terms`: customer qualification, delivery, share, order, capacity, and certification evidence.
- `invalidation_terms`: risks that weaken the thesis.
- `global_reference_entities`: non-scoring reference entities used for context, such as Samsung, SK hynix, Micron, Murata, Samsung Electro-Mechanics, TSMC, Nvidia.

`bottleneck_dimensions` is the key change. A chain can have multiple dimensions, and a candidate only needs strong evidence in at least one relevant dimension, not a generic "卡脖子" phrase.

## Initial Chain Definitions

### AI Optical Modules / Optical Communication

Context: optical modules, optical devices, optical engines, optical interconnect, data center interconnect, AI cluster networking.

Bottleneck dimensions:

- Bandwidth generation: `800G`, `1.6T`, `3.2T`, `高速光模块`.
- Architecture route: `硅光`, `CPO`, `LPO`, `NPO`, `光引擎`.
- Critical components: `EML`, `CW`, `FAU`, `DSP`, `光芯片`, `光器件`.
- Process delivery: `耦合`, `封装`, `良率`, `低功耗`, `高速率`.
- Customer delivery: `北美CSP`, `大客户导入`, `份额`, `交付`, `产能爬坡`.

### AI Chips / Compute Accelerators

Context: GPU, ASIC, NPU, AI accelerator, training chips, inference chips, chiplet compute, domestic AI chips.

Bottleneck dimensions:

- Process and architecture: `先进制程`, `chiplet`, `互联架构`, `片间互联`.
- Memory interface: `HBM接口`, `高带宽内存`, `封装协同`.
- Software stack: `编译器`, `算子库`, `推理框架`, `生态适配`.
- Qualification: `客户验证`, `集群部署`, `云端产品线`.

### HBM / High-End Memory

Context: HBM3, HBM3E, HBM4, high bandwidth memory, AI accelerator memory.

Bottleneck dimensions:

- Memory generation: `HBM3E`, `HBM4`, `12Hi`, `16Hi`.
- Stacking and TSV: `TSV`, `堆叠`, `base die`, `micro bump`.
- Packaging linkage: `CoWoS`, `2.5D`, `interposer`.
- Qualification and yield: `Nvidia认证`, `客户验证`, `良率`, `后段产能`.
- Supply allocation: `长协`, `产能分配`, `供给紧张`, `sold out`.

Reference entities: Samsung, SK hynix, Micron.

### Advanced Packaging

Context: 2.5D/3D packaging, CoWoS, SoIC, hybrid bonding, chiplet integration.

Bottleneck dimensions:

- Packaging platform: `CoWoS`, `SoIC`, `2.5D`, `3D`, `FOPLP`.
- Interconnect: `interposer`, `RDL`, `hybrid bonding`, `micro bump`.
- Materials and capacity: `T-glass`, `underfill`, `封装基板`, `先进封装产能`.
- Yield and qualification: `良率`, `可靠性验证`, `客户认证`.

### ABF / High-End Package Substrates

Context: ABF substrate, high-layer package substrates, AI GPU/ASIC substrates.

Bottleneck dimensions:

- Substrate grade: `ABF`, `高层数`, `低翘曲`, `大尺寸`.
- Materials: `玻纤布`, `树脂`, `低介电`, `低损耗`.
- Customer linkage: `AI GPU`, `ASIC`, `高端封装基板`.
- Supply tightness: `扩产`, `交期`, `产能紧张`.

### AI Server PCB

Context: AI server PCB, high-speed PCB, HDI, high-layer boards, switch PCB, backplanes.

Bottleneck dimensions:

- Product grade: `高速PCB`, `高阶HDI`, `高多层板`, `背板`, `交换机PCB`.
- Materials: `低损耗材料`, `高速覆铜板`, `高频高速板`.
- AI linkage: `AI服务器PCB`, `AIPCB`, `数据中心PCB`.
- Delivery: `高价值量产品`, `订单`, `客户导入`, `产能爬坡`.

### MLCC / High-End Passive Components

Context: MLCC, high-capacitance ceramic capacitors, AI server power delivery, GPU peripheral passives.

Bottleneck dimensions:

- Power density: `AI server PDN`, `GPU周边`, `高瞬态电流`.
- Product grade: `高容量`, `高温`, `高可靠`, `小型化`, `车规级`.
- Materials and process: `陶瓷粉体`, `介质材料`, `叠层`, `烧结`.
- Supply concentration: `Murata`, `Samsung Electro-Mechanics`, `Taiyo Yuden`.
- Capacity tightness: `涨价`, `交期`, `满产`, `长协`.

### Power Management / Power Delivery

Context: PMIC, DrMOS, VRM, server power modules, PDU, UPS, transformers, copper busbar.

Bottleneck dimensions:

- Board-level power: `PMIC`, `DrMOS`, `VRM`, `电源模块`.
- Data center power: `PDU`, `UPS`, `变压器`, `母线`, `配电`.
- Efficiency and reliability: `高效率`, `高可靠`, `大电流`, `低损耗`.
- Capacity: `交付`, `扩产`, `客户认证`.

### Liquid Cooling / Thermal Management

Context: direct-to-chip liquid cooling, cold plates, CDU, pumps, quick connectors, immersion cooling, TIM.

Bottleneck dimensions:

- Cooling architecture: `液冷`, `冷板`, `CDU`, `浸没式`.
- Components: `泵阀`, `快接头`, `管路`, `热界面材料`.
- Deployment: `数据中心`, `AI服务器`, `规模交付`, `客户验证`.

### Data Center Fiber / High-Speed Connectors

Context: optical fiber, MPO/MTP, high-speed connectors, DAC/AEC, copper cable, switch interconnect.

Bottleneck dimensions:

- Interconnect products: `MPO`, `MTP`, `高速连接器`, `DAC`, `AEC`.
- Signal integrity: `低损耗`, `高速传输`, `屏蔽`, `散热`.
- Data center linkage: `交换机`, `服务器互联`, `AI集群`.

### Semiconductor Equipment

Context: wafer fabrication, etch, deposition, cleaning, ion implantation, metrology, CMP, coating/development.

Bottleneck dimensions:

- Process equipment: `刻蚀`, `薄膜沉积`, `清洗`, `离子注入`, `热处理`.
- Metrology and testing: `量测`, `检测`, `探针台`, `分选机`.
- Domestic replacement: `国产替代`, `客户验证`, `先进制程`.
- Platformization: `平台型设备`, `工艺覆盖`, `设备组合`.

### Lithography / EDA / Semiconductor IP

Context: lithography, photoresist, EDA, IP core, design verification, advanced-node design flow.

Bottleneck dimensions:

- Design tools: `EDA`, `验证工具`, `仿真`, `布线`, `签核`.
- IP: `IP core`, `接口IP`, `处理器IP`.
- Lithography chain: `EUV`, `DUV`, `光刻胶`, `掩膜版`.
- Qualification: `先进节点`, `流片`, `客户导入`.

### Semiconductor Materials

Context: photoresist, electronic gases, wet chemicals, targets, CMP slurry/pads, silicon wafers, masks.

Bottleneck dimensions:

- Wafer materials: `硅片`, `外延`, `抛光片`.
- Chemicals: `电子特气`, `湿电子化学品`, `光刻胶`.
- CMP and targets: `CMP抛光液`, `抛光垫`, `靶材`.
- Qualification: `晶圆厂认证`, `批量供货`, `国产替代`.

### Power Semiconductors

Context: SiC, GaN, IGBT, MOSFET, power modules, automotive and industrial certification.

Bottleneck dimensions:

- Materials: `SiC衬底`, `外延`, `GaN`.
- Devices: `IGBT`, `MOSFET`, `功率模块`.
- Certification: `车规`, `工业认证`, `客户定点`.
- Capacity: `8英寸`, `产线`, `良率`.

### High-End Sensors

Context: CIS, MEMS, lidar, infrared, industrial vision, robot and automotive perception.

Bottleneck dimensions:

- Sensor type: `CIS`, `MEMS`, `激光雷达`, `红外`, `工业视觉`.
- Performance: `高精度`, `高可靠`, `低噪声`, `高速`.
- Qualification: `车载`, `机器人`, `客户认证`.

### Robotics Core Components

Context: reducers, ball screws, roller screws, torque motors, servo systems, controllers, dexterous hands, force sensors.

Bottleneck dimensions:

- Motion components: `减速器`, `丝杠`, `力矩电机`, `伺服`.
- Control and sensing: `控制器`, `六维力传感器`, `灵巧手`.
- Manufacturing: `精密加工`, `一致性`, `寿命`, `良率`.
- Customer validation: `机器人客户`, `量产`, `定点`.

### Industrial Software / Control Systems

Context: PLC, DCS, MES, CAD/CAE/CAM, industrial operating systems, real-time control.

Bottleneck dimensions:

- Control systems: `PLC`, `DCS`, `实时控制`, `工业操作系统`.
- Engineering software: `CAD`, `CAE`, `CAM`, `MES`.
- Replacement: `国产替代`, `自主可控`, `客户迁移`.
- Reliability: `稳定性`, `实时性`, `生态适配`.

### High-End Magnetic and Inductor Materials

Context: molded inductors, soft magnetic powder cores, nanocrystalline materials, AI server power passives.

Bottleneck dimensions:

- Passive power components: `一体成型电感`, `功率电感`, `软磁粉芯`.
- Materials: `纳米晶`, `非晶`, `磁粉芯`.
- AI server linkage: `高频`, `大电流`, `低损耗`, `电源周边`.

### High-End Ceramics / Electronic Materials

Context: ceramic substrates, AlN, alumina, LTCC, MLCC powders, dielectric materials.

Bottleneck dimensions:

- Substrates: `陶瓷基板`, `氮化铝`, `氧化铝`, `LTCC`.
- MLCC upstream: `陶瓷粉体`, `电容介质`, `高介电`.
- Reliability: `高导热`, `高可靠`, `低损耗`.

### Power Grid / Energy Infrastructure

Context: UHV, transformers, switchgear, energy storage, gas turbines, grid connection for data centers.

Bottleneck dimensions:

- Grid equipment: `特高压`, `变压器`, `开关`, `GIS`, `GIL`.
- Data center power: `数据中心供电`, `电力接入`, `配电`.
- Energy balancing: `储能`, `燃机`, `调峰`.
- Qualification: `中标`, `国网`, `南网`, `批量交付`.

## Data Flow

1. Candidate rows enter the existing topN / top100 pipeline.
2. `tech_chain_taxonomy` maps candidate text and PIT-safe evidence into one or more chain contexts.
3. Product exposure is evaluated against `product_exposure_terms`.
4. Evidence rows are mapped into chain-specific bottleneck dimensions and support buckets.
5. Quality review consumes normalized chain evidence instead of only generic buckets.
6. Miss audit reports the failing layer: topN, chain context, product exposure, bottleneck dimension, support evidence, or PIT safety.

## Decision Rules

P1 requires:

- A recognized chain context.
- PIT-safe product exposure linked to that chain.
- At least one strong chain-specific bottleneck dimension.
- Strong or medium-plus technical execution evidence.
- At least one strong support signal among customer validation, capacity delivery, catalyst, or supply tightness.
- No strong invalidation evidence that directly undermines the chain thesis.

P2 requires:

- A recognized chain context.
- One of product exposure, bottleneck dimension, or support evidence is incomplete but plausibly recoverable from PIT-safe sources.
- The candidate should be queued for targeted evidence backfill, not auto-promoted.

Reject requires one of:

- No chain context.
- Chain context exists but product exposure is missing and no PIT-safe source is available.
- Evidence is mainly generic sector heat, valuation, or future-only reports.
- Invalidation evidence directly contradicts the bottleneck thesis.

## Error Handling

- Unknown chain terms are not silently promoted. They enter `unmapped_chain_terms.csv`.
- Future-dated evidence cannot upgrade product exposure or bottleneck quality.
- Global reference entities are context only. Mentioning Samsung, SK hynix, Nvidia, Murata, or TSMC is not itself evidence for an A-share candidate.
- If a row maps to multiple chains, the review keeps all chain matches but selects the strongest chain by product exposure first, then bottleneck dimension score.

## Outputs

The implementation should produce:

- `tech_chain_taxonomy.json`: versioned chain definitions.
- `chain_mapping.csv`: candidate-to-chain mapping rows.
- `chain_evidence_review.csv`: evidence mapped to chain dimensions.
- `chain_quality_review.csv`: P1/P2/reject decisions with chain-specific reasons.
- `unmapped_chain_terms.csv`: terms that look hard-tech but are not yet in taxonomy.
- `chain_miss_audit.csv`: miss reasons for strong winners and operator watchlists.

## Validation Plan

Use three validation sets:

1. Core leader watchlist: 北方华创、新易盛、中际旭创、胜宏科技、寒武纪、天孚通信.
2. 2025-01-01 to latest clean strong-winner pool.
3. Existing top100 tech-bottleneck candidate pool.

Success criteria:

- AI optical leaders should fail for explainable PIT evidence gaps, not because the chain taxonomy does not know optical bottleneck dimensions.
- HBM, MLCC, advanced packaging, AI PCB, and AI optical chains should appear as explicit categories, not generic semiconductor or communication labels.
- P1 count should not inflate simply because more chains are recognized. The main first-order change should be improved P2 routing and better miss audit reasons.
- Existing semiconductor equipment/materials approvals should remain stable unless chain-specific invalidation evidence changes the decision.

## Implementation Boundaries

This design does not change ranking or portfolio construction. It only changes the tech-bottleneck discovery evidence layer.

The first implementation should avoid live web scraping. It should use existing evidence artifacts, official product rows, research report rows, and a versioned local taxonomy file.

The taxonomy should be readable and editable by a human reviewer. Code should treat it as configuration, not hard-coded branch logic.
