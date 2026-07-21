# AI PCB 证据缺口审查与定向研究设计基线 v1

> [RESEARCH DESIGN — NOT EVIDENCE] 本报告是集成 artifact 的确定性只读投影，不包含新增证据、瓶颈结论或价值迁移判断。

## 1. Execution boundary

- Execution mode: offline_read_only_research_design
- Network access: False
- New acquisition: False
- Evidence assessment of new sources: False

## 2. Fixed research groups

### group_a_signal_transmission: Group A — 信号与传输机理

Design research for signal integrity, insertion loss, channel reach/rate/topology and the technical drivers of layer count.

### group_b_material_capability: Group B — 材料能力

Design research for laminate, resin, dielectric and copper-surface variables plus reliability and processability trade-offs.

### group_c_manufacturing_testing: Group C — 制造与测试

Design research for process requirements, tolerances, reliability, test coverage and bounded manufacturing capability.

### group_d_bottleneck_effective_capacity: Group D — 产业瓶颈与有效产能

Design research that distinguishes nominal, qualified and effective capacity and identifies the public-evidence ceiling.

## 3. Gap reviews

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-BACKDRILL

- Group: group_c_manufacturing_testing
- Original gap: When and why are back-drilling processes required?
- Current grounded knowledge: The package contains no via-stub, back-drill tolerance, inspection, defect or reliability evidence.
- Current unknowns: Scoped technical threshold, manufacturing tolerance and bounded process/reliability consequences.
- Public evidence availability: likely_publicly_available
- Public evidence ceiling: engineering_difficulty_only
- Comparison denominator: per named via structure, stack-up, frequency/rate, process window and lot/product class
- Required evidence types: via/channel engineering study; process and acceptance standard; failure/reliability data
- Suggested source classes: peer_reviewed_engineering; technical_standard; pcb_process_engineering; failure_analysis
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: high — Tests whether a technical mitigation creates bounded manufacturing difficulty without inferring industry bottlenecks.
- Dependencies: GAP-SIGNAL; GAP-LOSS
- Future acquisition authorized: False

Atomic research questions:

- GAP-BACKDRILL-Q01: For a defined via structure and channel, when does residual stub behavior require mitigation? [ER: PCB-ER-C01]
- GAP-BACKDRILL-Q02: What manufacturing tolerance and verification method define an acceptable back-drill result? [ER: PCB-ER-C02]
- GAP-BACKDRILL-Q03: What scoped defect and reliability evidence would show back-drill adds manufacturing difficulty? [ER: PCB-ER-C03]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-CAPACITY

- Group: group_d_bottleneck_effective_capacity
- Original gap: How should qualified effective capacity be distinguished from nominal PCB capacity?
- Current grounded knowledge: Current evidence contains no comparable nominal, configured, qualified or yield-adjusted PCB capacity series.
- Current unknowns: Capacity definitions, qualification/ramp adjustments, demand denominator, persistence and relief/substitution paths.
- Public evidence availability: structurally_limited
- Public evidence ceiling: structurally_limited
- Comparison denominator: qualified good-output capacity and matched demand per product specification, region and period
- Required evidence types: capacity definitions and industry statistics; qualification/ramp/utilization/mix/yield data; demand/lead-time/delivery evidence; relief/substitution evidence
- Suggested source classes: industry_statistics; audited_manufacturing_data; customer_qualification_record; independent_industry_research
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: deferred — Effective capacity cannot be assessed before yield/qualification and matched demand denominators; public evidence may remain structurally incomplete.
- Dependencies: GAP-YIELD
- Future acquisition authorized: False

Atomic research questions:

- GAP-CAPACITY-Q01: What definitions and denominators distinguish nominal, configured, qualified and effective capacity? [ER: PCB-ER-D01]
- GAP-CAPACITY-Q02: What evidence describes qualification, ramp, utilization, mix and yield constraints on effective output? [ER: PCB-ER-D02]
- GAP-CAPACITY-Q03: What demand, lead-time or delivery evidence would be required before calling an effective-capacity constraint a commercial shortage? [ER: PCB-ER-D03]
- GAP-CAPACITY-Q04: What relief, substitution or additional qualified supply could invalidate a capacity-constraint hypothesis? [ER: PCB-ER-D04]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-LAMINATE

- Group: group_b_material_capability
- Original gap: Which laminate and resin properties are required by the relevant channel budgets?
- Current grounded knowledge: No current evidence locator grounds laminate, resin, dielectric or copper-surface behavior.
- Current unknowns: Measurement-method comparability, controlled property effects, reliability/processability trade-offs and substitution criteria.
- Public evidence availability: likely_publicly_available
- Public evidence ceiling: technical_understanding_only
- Comparison denominator: property/performance per named construction, method, frequency, temperature and application
- Required evidence types: material data with test method; independent material measurement; reliability and processability tests
- Suggested source classes: vendor_material_datasheet; technical_standard; independent_material_test; peer_reviewed_engineering
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: critical — Material claims cannot be interpreted before signal/loss scope and methods are fixed.
- Dependencies: GAP-LOSS
- Future acquisition authorized: False

Atomic research questions:

- GAP-LAMINATE-Q01: Which material properties are measured, by what method and at what frequency/temperature for the scoped channel? [ER: PCB-ER-B01]
- GAP-LAMINATE-Q02: How do copper profile and surface treatment enter a controlled material/channel comparison? [ER: PCB-ER-B02]
- GAP-LAMINATE-Q03: What reliability and processability attributes constrain a technically suitable material choice? [ER: PCB-ER-B03]
- GAP-LAMINATE-Q04: Under what evidence can two material grades be considered technically substitutable for a scoped application? [ER: PCB-ER-B04]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-LAMINATION

- Group: group_c_manufacturing_testing
- Original gap: How do lamination and layer alignment affect manufacturability?
- Current grounded knowledge: No current evidence grounds lamination cycles, registration tolerance, equipment capability or process distributions.
- Current unknowns: Required tolerances, complexity effects and publicly observable process-capability bounds.
- Public evidence availability: partially_publicly_available
- Public evidence ceiling: engineering_difficulty_only
- Comparison denominator: per named layer count, panel size, material construction, process cycle and acceptance class
- Required evidence types: lamination/registration standard; process capability study; reliability comparison
- Suggested source classes: technical_standard; pcb_process_engineering; equipment_engineering; independent_manufacturing_study
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: high — Separates specified tolerances from actual factory capability and yield.
- Dependencies: GAP-LAYERS; GAP-LAMINATE
- Future acquisition authorized: False

Atomic research questions:

- GAP-LAMINATION-Q01: What registration and lamination tolerances are required for a defined multilayer structure? [ER: PCB-ER-C04]
- GAP-LAMINATION-Q02: What observed process-capability distribution would demonstrate bounded alignment or lamination capability? [ER: PCB-ER-C05]
- GAP-LAMINATION-Q03: How do additional lamination cycles or stack complexity change process steps and reliability requirements? [ER: PCB-ER-C06]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-LAYERS

- Group: group_a_signal_transmission
- Original gap: What directly drives PCB layer-count changes in the relevant AI systems?
- Current grounded knowledge: Current cognition describes system and interconnect topology; it contains no verified board stack-up, schematic or teardown evidence.
- Current unknowns: Functional layer allocation, cross-generation comparability and whether observed layer choices are mandatory or architectural.
- Public evidence availability: partially_publicly_available
- Public evidence ceiling: technical_understanding_only
- Comparison denominator: layers per matched board function, form factor, area, topology and generation
- Required evidence types: verified stack-up or teardown; board-function allocation; generation-normalized engineering comparison
- Suggested source classes: engineering_teardown; board_stackup_disclosure; independent_pcb_engineering
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: high — Prevents using unverified layer-count narratives as manufacturing evidence.
- Dependencies: GAP-SIGNAL
- Future acquisition authorized: False

Atomic research questions:

- GAP-LAYERS-Q01: For a defined board function, what functional needs account for the disclosed layer stack? [ER: PCB-ER-A07]
- GAP-LAYERS-Q02: How can layer-count changes across generations be compared without mixing board size, function or topology? [ER: PCB-ER-A08]
- GAP-LAYERS-Q03: Which observed layer-count drivers are technical requirements and which are design choices or packaging constraints? [ER: PCB-ER-A09]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-LOSS

- Group: group_a_signal_transmission
- Original gap: How do insertion-loss mechanisms change PCB material and geometry requirements?
- Current grounded knowledge: Current evidence establishes system interconnect roles but contains no comparable insertion-loss data or test methods.
- Current unknowns: Comparable loss definition, variable contributions and the mapping from a scoped channel budget to material/geometry constraints.
- Public evidence availability: likely_publicly_available
- Public evidence ceiling: technical_understanding_only
- Comparison denominator: dB per specified length/frequency/channel construction and measurement method
- Required evidence types: loss measurement standards; controlled coupon/channel measurements; validated channel-budget analysis
- Suggested source classes: technical_standard; peer_reviewed_engineering; independent_material_test
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: critical — Required before material-property questions can be interpreted.
- Dependencies: GAP-SIGNAL
- Future acquisition authorized: False

Atomic research questions:

- GAP-LOSS-Q01: What definition and test method make insertion-loss values comparable? [ER: PCB-ER-A04]
- GAP-LOSS-Q02: Within a controlled channel, what measured contribution is associated with dielectric, conductor surface and geometry variables? [ER: PCB-ER-A05]
- GAP-LOSS-Q03: What scoped channel budget would require a material or geometry constraint, without inferring manufacturing or market effects? [ER: PCB-ER-A06]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-SIGNAL

- Group: group_a_signal_transmission
- Original gap: How do higher data rates change signal-integrity constraints?
- Current grounded knowledge: Existing cognition grounds interface, topology and product-level bandwidth facts on the AI-system demand side.; No normalized section in the current package provides PCB signal-integrity measurement or mechanism evidence.
- Current unknowns: The scoped electrical channel, measurement variables, boundary conditions and rate/reach relationship.
- Public evidence availability: likely_publicly_available
- Public evidence ceiling: technical_understanding_only
- Comparison denominator: per lane/channel at named rate, reach, topology, frequency and test method
- Required evidence types: interface definitions; signal-integrity standards; measured channel data
- Suggested source classes: technical_standard; peer_reviewed_engineering; test_equipment_engineering
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: critical — Defines the physical boundary for every later PCB-side mechanism.
- Dependencies: 
- Future acquisition authorized: False

Atomic research questions:

- GAP-SIGNAL-Q01: What channel endpoints, topology, electrical reach, signaling generation and operating conditions define the scoped comparison? [ER: PCB-ER-A01]
- GAP-SIGNAL-Q02: Under the scoped channel, how do measured compliance variables change across data rate or reach? [ER: PCB-ER-A02]
- GAP-SIGNAL-Q03: Which boundary conditions or alternative explanations limit a claimed rate-to-signal-integrity relationship? [ER: PCB-ER-A03]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-TEST

- Group: group_c_manufacturing_testing
- Original gap: What test methods and equipment are required for high-speed boards?
- Current grounded knowledge: The current package has no PCB production-test standard, coverage, correlation, throughput or defect-escape data.
- Current unknowns: Required tests, actual production capability and trade-offs between coverage, repeatability and throughput.
- Public evidence availability: partially_publicly_available
- Public evidence ceiling: manufacturing_capability_bounded
- Comparison denominator: per product family, test flow, lot/unit population, method and observation period
- Required evidence types: test/acceptance standard; instrument method and correlation; production coverage and defect data
- Suggested source classes: technical_standard; test_equipment_engineering; qualified_manufacturing_data; failure_analysis
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: high — Test requirements can be public while actual coverage and defect escape may remain bounded.
- Dependencies: GAP-SIGNAL; GAP-LOSS
- Future acquisition authorized: False

Atomic research questions:

- GAP-TEST-Q01: Which electrical and structural tests are required for a defined high-speed board and acceptance class? [ER: PCB-ER-C10]
- GAP-TEST-Q02: What evidence demonstrates production test coverage, repeatability and correlation to reference measurements? [ER: PCB-ER-C11]
- GAP-TEST-Q03: What throughput, false-pass/false-fail and defect-escape trade-offs constrain the test flow? [ER: PCB-ER-C12]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-THERMAL

- Group: group_c_manufacturing_testing
- Original gap: How do thermal and electrical constraints interact at board level?
- Current grounded knowledge: Existing system documents provide demand-side product context but no board-level thermal-mechanical load or reliability evidence.
- Current unknowns: Applicable load case, measured failure relationship and resulting process/test controls.
- Public evidence availability: likely_publicly_available
- Public evidence ceiling: engineering_difficulty_only
- Comparison denominator: per named board/system, load case, material stack, reliability test and time window
- Required evidence types: board thermal-mechanical study; reliability/failure analysis; process/test control evidence
- Suggested source classes: system_thermal_design; reliability_standard; peer_reviewed_engineering; failure_analysis
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: high — Prevents system power figures from being treated as board manufacturing evidence.
- Dependencies: GAP-LAMINATE
- Future acquisition authorized: False

Atomic research questions:

- GAP-THERMAL-Q01: What board-level thermal and mechanical load case is relevant to the scoped AI system? [ER: PCB-ER-C07]
- GAP-THERMAL-Q02: What measured failure or reliability relationship connects the load case to board materials or structure? [ER: PCB-ER-C08]
- GAP-THERMAL-Q03: What manufacturing or test-control requirements follow from the verified thermal-mechanical condition? [ER: PCB-ER-C09]

### [RESEARCH DESIGN — NOT EVIDENCE] GAP-YIELD

- Group: group_c_manufacturing_testing
- Original gap: Which process steps constrain qualified manufacturing yield?
- Current grounded knowledge: No current artifact provides denominator-defined PCB yield, process-step loss, defect Pareto or qualification time series.
- Current unknowns: Yield definition, product mix, process-loss attribution and whether observed issues are temporary ramp effects or persistent constraints.
- Public evidence availability: structurally_limited
- Public evidence ceiling: structurally_limited
- Comparison denominator: qualified good units divided by defined inputs per product, process/facility, qualification state and period
- Required evidence types: audited denominator-defined yield; process defect Pareto; qualification/ramp time series
- Suggested source classes: audited_manufacturing_data; failure_analysis; customer_qualification_record; independent_manufacturing_study
- Minimum sufficiency: Every linked atomic ER reaches its own sufficiency rule under a compatible scope.; Required independent chains and contradiction search are complete.; No critical denominator, generation or method conflict remains unresolved.
- Stop conditions: Stop as resolved only when all minimum sufficiency conditions are met.; Stop as bounded_by_public_evidence when technical understanding is possible but higher cognition requires non-public data.; Stop as stopped_due_to_structural_limit when yield, qualification, mix or qualified output cannot be independently observed.; Stop as stopped_due_to_redundancy when new sources trace to existing chains or no longer change the research state.; Stop as stopped_due_to_scope when generation, product class, method or denominator cannot be reconciled.
- Non-derivable conclusions: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.
- Priority: deferred — Public evidence often cannot reveal internal product mix, process windows or qualified yield; review only after manufacturing ERs.
- Dependencies: GAP-BACKDRILL; GAP-LAMINATION; GAP-THERMAL; GAP-TEST
- Future acquisition authorized: False

Atomic research questions:

- GAP-YIELD-Q01: What denominator, product mix and qualification state define a reported manufacturing yield? [ER: PCB-ER-C13]
- GAP-YIELD-Q02: Which process-step loss or defect Pareto is supported by denominator-defined data? [ER: PCB-ER-C14]
- GAP-YIELD-Q03: What evidence would distinguish a temporary ramp yield issue from a persistent process constraint? [ER: PCB-ER-C15]

## 4. Atomic Evidence Requirements

### PCB-ER-A01 (GAP-SIGNAL)

What channel endpoints, topology, electrical reach, signaling generation and operating conditions define the scoped comparison?

- Claim scope: atomic_research_design_requirement
- Required fact types: interface generation; channel topology; electrical reach; endpoint definition; operating conditions
- Required source classes: technical_standard; official_interface_specification
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One named interface generation and one defined board/channel topology.
- Denominator: per channel, per lane and per named interface generation
- Sufficiency: A normative definition and an independent engineering interpretation agree on endpoints, topology, rate and measurement conditions.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when the scoped channel is unambiguous; stop due to scope if product generation or topology cannot be fixed.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-A02 (GAP-SIGNAL)

Under the scoped channel, how do measured compliance variables change across data rate or reach?

- Claim scope: atomic_research_design_requirement
- Required fact types: insertion loss measurement; return loss measurement; crosstalk measurement; jitter or eye metric; test method
- Required source classes: technical_standard; peer_reviewed_engineering; test_equipment_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Same channel class measured at comparable rates or reaches.
- Denominator: per lane at specified frequency/rate, length and fixture de-embedding method
- Sufficiency: At least one direct measurement with method plus one independent corroborating chain provides comparable variables and uncertainty.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when comparable measurements satisfy the minimum; stop due to denominator if fixtures, frequency or reach cannot be reconciled.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-A03 (GAP-SIGNAL)

Which boundary conditions or alternative explanations limit a claimed rate-to-signal-integrity relationship?

- Claim scope: atomic_research_design_requirement
- Required fact types: boundary condition; alternative topology; equalization condition; measurement uncertainty
- Required source classes: peer_reviewed_engineering; technical_standard; independent_engineering_validation
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Same interface family with explicitly different topology, equalization or reach.
- Denominator: per normalized channel condition
- Sufficiency: A supporting relationship and at least one independent limiting or counter case are both scoped.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when further sources repeat the same experiment or no longer change the identified boundary conditions.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-A04 (GAP-LOSS)

What definition and test method make insertion-loss values comparable?

- Claim scope: atomic_research_design_requirement
- Required fact types: loss definition; frequency point or band; test coupon geometry; fixture removal method; temperature condition
- Required source classes: technical_standard; test_equipment_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One measurement method applied to a defined PCB channel or coupon.
- Denominator: dB per specified length at specified frequency and test method
- Sufficiency: A normative method and an independent implementation guide define comparable units, frequency, geometry and de-embedding.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop due to denominator when loss values lack compatible frequency, length or method.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-A05 (GAP-LOSS)

Within a controlled channel, what measured contribution is associated with dielectric, conductor surface and geometry variables?

- Claim scope: atomic_research_design_requirement
- Required fact types: dielectric-loss measurement; conductor-loss measurement; surface-profile measurement; geometry-controlled comparison
- Required source classes: peer_reviewed_engineering; independent_material_test; technical_standard
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Matched coupons or models changing one declared variable at a time.
- Denominator: loss per unit length at matched frequency, geometry, copper weight and method
- Sufficiency: Controlled measurements or validated models isolate variables, state uncertainty and are independently corroborated.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when variable isolation is not possible or all sources ultimately reuse one supplier dataset.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-A06 (GAP-LOSS)

What scoped channel budget would require a material or geometry constraint, without inferring manufacturing or market effects?

- Claim scope: atomic_research_design_requirement
- Required fact types: channel loss budget; allocated board loss; reach requirement; design margin
- Required source classes: technical_standard; system_engineering_document; peer_reviewed_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One interface/channel budget and an explicitly mapped PCB portion.
- Denominator: dB budget per lane, reach and generation
- Sufficiency: The channel budget, allocation method and mapped material/geometry requirement are explicit and independently checked.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at technical understanding; do not continue toward supply or value conclusions without separate ERs.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-A07 (GAP-LAYERS)

For a defined board function, what functional needs account for the disclosed layer stack?

- Claim scope: atomic_research_design_requirement
- Required fact types: verified stack-up; signal-layer allocation; power-ground allocation; escape-routing requirement; mechanical constraint
- Required source classes: engineering_teardown; board_stackup_disclosure; independent_pcb_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Same board function, form factor and system generation.
- Denominator: layers per specified board function and form factor
- Sufficiency: A verified stack-up or teardown identifies layer functions and an independent engineer corroborates the allocation.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop if stack-up identity, board function or provenance cannot be verified.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-A08 (GAP-LAYERS)

How can layer-count changes across generations be compared without mixing board size, function or topology?

- Claim scope: atomic_research_design_requirement
- Required fact types: generation-matched stack-up; board area; component density; topology change; power-delivery change
- Required source classes: engineering_teardown; board_stackup_disclosure; independent_pcb_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Matched board function across two named generations.
- Denominator: layer delta per matched board function, area and topology
- Sufficiency: At least two generation-specific records normalize board function, area, topology and power-delivery differences.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop due to denominator if the compared boards perform different functions or use unknown stack-ups.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-A09 (GAP-LAYERS)

Which observed layer-count drivers are technical requirements and which are design choices or packaging constraints?

- Claim scope: atomic_research_design_requirement
- Required fact types: driver classification; alternative stack-up; routing-density evidence; power-integrity evidence
- Required source classes: peer_reviewed_engineering; engineering_teardown; technical_standard
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One board class with at least one plausible alternative design.
- Denominator: per matched board function and requirement set
- Sufficiency: Evidence distinguishes mandatory compliance requirements from optional architecture or packaging choices.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when alternatives cannot be compared under the same requirement set.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-B01 (GAP-LAMINATE)

Which material properties are measured, by what method and at what frequency/temperature for the scoped channel?

- Claim scope: atomic_research_design_requirement
- Required fact types: Dk measurement; Df measurement; test method; frequency; temperature; material construction
- Required source classes: vendor_material_datasheet; technical_standard; independent_material_test
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Named laminate construction and applicable channel frequency range.
- Denominator: property value per test method, frequency, temperature and construction
- Sufficiency: A supplier declaration states method and conditions and an independent test or standard makes the value interpretable.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop if property values lack method, frequency or construction; do not compare unlike methods.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-B02 (GAP-LAMINATE)

How do copper profile and surface treatment enter a controlled material/channel comparison?

- Claim scope: atomic_research_design_requirement
- Required fact types: surface-profile metric; copper treatment; matched dielectric construction; measured channel loss
- Required source classes: independent_material_test; peer_reviewed_engineering; vendor_material_datasheet
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Matched dielectric and geometry with declared copper profile/treatment.
- Denominator: loss per unit length at matched frequency, geometry and method
- Sufficiency: Controlled measurements isolate copper profile/treatment and include an independent chain.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when copper and dielectric changes cannot be separated or sources reuse one supplier test.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-B03 (GAP-LAMINATE)

What reliability and processability attributes constrain a technically suitable material choice?

- Claim scope: atomic_research_design_requirement
- Required fact types: thermal reliability metric; moisture metric; adhesion metric; lamination/process condition; failure mode
- Required source classes: technical_standard; independent_material_test; peer_reviewed_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Named material construction under a defined reliability or processing test.
- Denominator: pass/fail or measured property per named test condition
- Sufficiency: At least one standardized or peer-reviewed test and one independent corroboration identify the applicable trade-off.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at material-level trade-offs; do not infer factory capability or yield.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-B04 (GAP-LAMINATE)

Under what evidence can two material grades be considered technically substitutable for a scoped application?

- Claim scope: atomic_research_design_requirement
- Required fact types: matched property set; channel performance; reliability result; qualification boundary
- Required source classes: independent_material_test; technical_standard; system_engineering_document
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Same application, construction, test methods and acceptance thresholds.
- Denominator: per matched application and qualification test set
- Sufficiency: Comparable technical and reliability results meet an explicit application threshold with independent corroboration.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop if qualification criteria or material constructions differ; do not infer commercial availability.
- Maximum supported cognition level: technical_understanding
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C01 (GAP-BACKDRILL)

For a defined via structure and channel, when does residual stub behavior require mitigation?

- Claim scope: atomic_research_design_requirement
- Required fact types: via geometry; residual stub length; frequency/rate; measured channel response; acceptance threshold
- Required source classes: peer_reviewed_engineering; technical_standard; independent_engineering_validation
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One named via/channel structure and interface generation.
- Denominator: response per residual-stub length at specified frequency and geometry
- Sufficiency: Direct measurement or validated model identifies a scoped threshold and an independent chain corroborates it.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at the engineering requirement; do not infer production bottleneck.
- Maximum supported cognition level: manufacturing_difficulty
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C02 (GAP-BACKDRILL)

What manufacturing tolerance and verification method define an acceptable back-drill result?

- Claim scope: atomic_research_design_requirement
- Required fact types: depth tolerance; registration tolerance; inspection method; reliability acceptance
- Required source classes: pcb_process_engineering; technical_standard; test_equipment_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Named stack-up, drill structure and acceptance standard.
- Denominator: tolerance distribution per stack-up and inspection method
- Sufficiency: A process/acceptance standard and independent capability evidence define tolerance and inspection.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop if only nominal equipment capability is public; label actual production capability bounded.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C03 (GAP-BACKDRILL)

What scoped defect and reliability evidence would show back-drill adds manufacturing difficulty?

- Claim scope: atomic_research_design_requirement
- Required fact types: defect mode; rework or scrap event; reliability failure; process-control result
- Required source classes: failure_analysis; pcb_process_engineering; qualified_manufacturing_data
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One product class and controlled process window.
- Denominator: defect or failure rate per defined lot/product/process window
- Sufficiency: A scoped process dataset plus an independent failure/reliability chain links the step to outcomes.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at bounded manufacturing capability; do not generalize to industry yield or capacity.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C04 (GAP-LAMINATION)

What registration and lamination tolerances are required for a defined multilayer structure?

- Claim scope: atomic_research_design_requirement
- Required fact types: layer count; material construction; registration tolerance; lamination cycle; acceptance criterion
- Required source classes: technical_standard; pcb_process_engineering; equipment_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Named multilayer construction and acceptance class.
- Denominator: tolerance per layer count, panel size, material and process cycle
- Sufficiency: A standard or engineering study states the tolerance and an independent source explains measurement or control.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop if panel size, material or acceptance class is absent.
- Maximum supported cognition level: manufacturing_difficulty
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C05 (GAP-LAMINATION)

What observed process-capability distribution would demonstrate bounded alignment or lamination capability?

- Claim scope: atomic_research_design_requirement
- Required fact types: process capability distribution; registration measurement; warpage/void result; lot definition
- Required source classes: qualified_manufacturing_data; pcb_process_engineering; independent_manufacturing_study
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One product family, line/process and observation window.
- Denominator: distribution per lot, product family and process window
- Sufficiency: A denominator-defined capability distribution and an independent corroborating chain are available.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop due to structural limit if only equipment specifications or marketing claims are public.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C06 (GAP-LAMINATION)

How do additional lamination cycles or stack complexity change process steps and reliability requirements?

- Claim scope: atomic_research_design_requirement
- Required fact types: process-step count; lamination-cycle count; material interaction; reliability test
- Required source classes: pcb_process_engineering; peer_reviewed_engineering; technical_standard
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Matched product class with declared stack complexity.
- Denominator: process/reliability delta per matched stack construction
- Sufficiency: Engineering evidence isolates complexity/cycle differences and records reliability outcomes.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at manufacturing difficulty; do not infer yield loss without denominator-defined yield data.
- Maximum supported cognition level: manufacturing_difficulty
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C07 (GAP-THERMAL)

What board-level thermal and mechanical load case is relevant to the scoped AI system?

- Claim scope: atomic_research_design_requirement
- Required fact types: temperature profile; power/heat boundary; mechanical constraint; material stack; test condition
- Required source classes: system_thermal_design; technical_standard; peer_reviewed_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Named board/system class and operating/test condition.
- Denominator: temperature or strain per location, load case and time window
- Sufficiency: A system/board load case and an independent engineering interpretation establish the scoped condition.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop if only system-level power is known without board-level boundary conditions.
- Maximum supported cognition level: manufacturing_difficulty
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C08 (GAP-THERMAL)

What measured failure or reliability relationship connects the load case to board materials or structure?

- Claim scope: atomic_research_design_requirement
- Required fact types: failure mode; thermal-cycle result; warpage/strain measurement; material/stack variable
- Required source classes: reliability_standard; failure_analysis; peer_reviewed_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Matched material/stack under a named reliability test.
- Denominator: failure/pass metric per named cycle, load and construction
- Sufficiency: A standardized or peer-reviewed test links a scoped variable to a measured outcome with independent corroboration.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at engineering difficulty; do not infer production yield.
- Maximum supported cognition level: manufacturing_difficulty
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C09 (GAP-THERMAL)

What manufacturing or test-control requirements follow from the verified thermal-mechanical condition?

- Claim scope: atomic_research_design_requirement
- Required fact types: process control; inspection criterion; test coverage; acceptance threshold
- Required source classes: pcb_process_engineering; test_equipment_engineering; technical_standard
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Same board class and verified thermal-mechanical condition.
- Denominator: control/acceptance result per defined process and test
- Sufficiency: A documented control requirement and bounded capability evidence are both present.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop if actual process capability is non-public; do not infer capacity.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C10 (GAP-TEST)

Which electrical and structural tests are required for a defined high-speed board and acceptance class?

- Claim scope: atomic_research_design_requirement
- Required fact types: test parameter; instrument/method; sampling rule; acceptance criterion; board class
- Required source classes: technical_standard; test_equipment_engineering; pcb_process_engineering
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Named board class, interface generation and acceptance standard.
- Denominator: test requirement per board class and acceptance level
- Sufficiency: A standard defines the test/acceptance requirement and an independent engineering source explains implementation limits.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when requirements are clear; do not infer actual factory coverage.
- Maximum supported cognition level: manufacturing_difficulty
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C11 (GAP-TEST)

What evidence demonstrates production test coverage, repeatability and correlation to reference measurements?

- Claim scope: atomic_research_design_requirement
- Required fact types: coverage matrix; repeatability/reproducibility; correlation result; sampling denominator
- Required source classes: qualified_manufacturing_data; test_equipment_engineering; independent_manufacturing_study
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One product family, test flow and observation window.
- Denominator: coverage/correlation per product, lot and test method
- Sufficiency: A denominator-defined production result and independent method/correlation evidence are available.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop due to structural limit if only instrument specifications are public.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C12 (GAP-TEST)

What throughput, false-pass/false-fail and defect-escape trade-offs constrain the test flow?

- Claim scope: atomic_research_design_requirement
- Required fact types: test time; false-pass rate; false-fail rate; defect escape; sampling rule
- Required source classes: qualified_manufacturing_data; test_equipment_engineering; failure_analysis
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One product/test flow and defined defect population.
- Denominator: rate per tested unit/lot and named method
- Sufficiency: A scoped dataset reports denominators and an independent chain validates the trade-off.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at bounded test capability; do not infer industry capacity or economics.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C13 (GAP-YIELD)

What denominator, product mix and qualification state define a reported manufacturing yield?

- Claim scope: atomic_research_design_requirement
- Required fact types: yield definition; lot/unit denominator; product mix; process stage; qualification state; time period
- Required source classes: audited_manufacturing_data; independent_manufacturing_study
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One product family, facility/process, qualification state and period.
- Denominator: good qualified units divided by defined input units per product/process/period
- Sufficiency: Yield definition and denominator are explicit and independently corroborated.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop due to structural limit when mix, stage, qualification or denominator is undisclosed.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C14 (GAP-YIELD)

Which process-step loss or defect Pareto is supported by denominator-defined data?

- Claim scope: atomic_research_design_requirement
- Required fact types: process-step loss; defect category; Pareto share; lot denominator; time series
- Required source classes: audited_manufacturing_data; failure_analysis; independent_manufacturing_study
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One product/process family and stable observation period.
- Denominator: defects or lost units per lot/input at each process step
- Sufficiency: A scoped Pareto with denominator and independent failure/process evidence is available.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when all public claims trace to one enterprise statement or omit denominators.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-C15 (GAP-YIELD)

What evidence would distinguish a temporary ramp yield issue from a persistent process constraint?

- Claim scope: atomic_research_design_requirement
- Required fact types: time series; generation/ramp stage; process change; qualification milestone; recovery evidence
- Required source classes: audited_manufacturing_data; customer_qualification_record; independent_industry_research
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Same product generation and facility/process across a sufficient time window.
- Denominator: yield/qualification metric per period and ramp stage
- Sufficiency: A dated series and independent qualification/process evidence distinguish recovery from persistence.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at structurally limited if no independent time series or qualification evidence is public.
- Maximum supported cognition level: manufacturing_capability_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-D01 (GAP-CAPACITY)

What definitions and denominators distinguish nominal, configured, qualified and effective capacity?

- Claim scope: atomic_research_design_requirement
- Required fact types: capacity definition; equipment/configuration; product mix; qualified product scope; yield/utilization adjustment
- Required source classes: industry_statistics; audited_manufacturing_data; independent_industry_research
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: One product class, facility/region and observation period.
- Denominator: qualified good-output capacity per product class and period
- Sufficiency: Capacity categories, adjustments and product scope are explicit and independently reconciled.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop due to denominator when nameplate area, revenue capacity and qualified output cannot be reconciled.
- Maximum supported cognition level: effective_capacity_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-D02 (GAP-CAPACITY)

What evidence describes qualification, ramp, utilization, mix and yield constraints on effective output?

- Claim scope: atomic_research_design_requirement
- Required fact types: qualification timeline; ramp status; utilization; product mix; yield-adjusted output
- Required source classes: customer_qualification_record; audited_manufacturing_data; independent_industry_research
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Same product class, facility/region and dated period.
- Denominator: qualified good output per period after utilization, mix and yield adjustments
- Sufficiency: At least two independent chains jointly cover qualification and output adjustments with compatible scope.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop at structurally limited when customer, product mix or qualified output is non-public.
- Maximum supported cognition level: effective_capacity_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-D03 (GAP-CAPACITY)

What demand, lead-time or delivery evidence would be required before calling an effective-capacity constraint a commercial shortage?

- Claim scope: atomic_research_design_requirement
- Required fact types: demand denominator; lead time; delivery performance; backlog/order quality; substitution availability
- Required source classes: industry_statistics; customer_primary; independent_industry_research
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Matched product specification, region and period.
- Denominator: demand and qualified supply per product specification and period
- Sufficiency: Independent demand and qualified-supply evidence share a denominator and show persistence beyond a temporary ramp.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop without a commercial-shortage conclusion if demand quality, product scope or duration cannot be established.
- Maximum supported cognition level: effective_capacity_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.

### PCB-ER-D04 (GAP-CAPACITY)

What relief, substitution or additional qualified supply could invalidate a capacity-constraint hypothesis?

- Claim scope: atomic_research_design_requirement
- Required fact types: new qualified capacity; substitution path; qualification time; demand change; lead-time normalization
- Required source classes: industry_statistics; customer_qualification_record; independent_industry_research
- Independent evidence chains: 2
- Supplier-independent source required: True
- Freshness: Use the applicable standard revision and match interface generation, frequency range, product class and observation period; unknown dates cannot establish current applicability.
- Comparison scope: Same specification, qualification standard, region and time horizon.
- Denominator: incremental qualified output or substitutable demand per period
- Sufficiency: At least one independent relief/substitution scenario is quantified against the same denominator.
- Contradiction search: Search for a conflicting measurement, alternative mechanism, boundary condition or incompatible denominator from a substantively independent evidence chain.
- Stop rule: Stop when additional sources no longer change the bounded scenarios; value migration remains out of scope.
- Maximum supported cognition level: effective_capacity_bounded
- Prohibited inferences: Technical difficulty does not establish a manufacturing bottleneck.; Manufacturing difficulty does not establish insufficient qualified effective capacity.; Effective-capacity limits do not establish price, margin or value migration.; Industry evidence does not establish a specific company's exposure or investment value.; Even a persistent shortage cannot establish value migration without separate cost, price and profit-allocation evidence.

## 5. Source-class boundaries

- audited_manufacturing_data: can support scoped yield; utilization; mix or output when denominator-defined; cannot support industry generalization without coverage; value migration without price/cost evidence.
- customer_qualification_record: can support scoped qualification status; timeline; acceptance requirement; cannot support total industry capacity; profit capture; equity value.
- independent_industry_research: can support triangulation; scope comparison; supply-demand interpretation; cannot support replace missing primary measurements; prove internal yield; automatically establish value migration.
- independent_material_test: can support comparative measured material performance; method-specific reliability evidence; cannot support production yield; qualified capacity; commercial adoption.
- industry_statistics: can support scoped shipment; capacity; lead-time or demand series with denominator; cannot support technical mechanism; company-specific qualification; profit allocation.
- pcb_process_engineering: can support process steps; tolerances; engineering process windows; failure modes; cannot support industry-wide yield; effective capacity; persistent shortage.
- peer_reviewed_engineering: can support physical mechanism; controlled comparison; measurement uncertainty; boundary conditions; cannot support industry-wide manufacturing capability; current capacity; company economics.
- technical_standard: can support definitions; measurement methods; compliance limits; test conditions; cannot support actual production yield; qualified effective capacity; commercial shortage; value migration.
- test_equipment_engineering: can support instrument capability; measurement method; test implementation limits; cannot support actual factory coverage; defect escape; commercial bottleneck.
- vendor_material_datasheet: can support declared material properties; supplier test method and conditions; cannot support independent comparative performance; factory yield; industry bottleneck; value migration.

## 6. Cross-level inference prohibitions

- LEVEL-01: technical_parameter_or_mechanism != manufacturing_bottleneck — Manufacturing-process capability, tolerance, reliability and production evidence are separately required.
- LEVEL-02: manufacturing_difficulty != effective_capacity_shortage — Qualified yield, utilization, product mix, qualification and output denominators are separately required.
- LEVEL-03: effective_capacity_constraint != commercial_supply_bottleneck — Matched demand, delivery, lead-time, duration and substitution evidence are separately required.
- LEVEL-04: commercial_supply_bottleneck != value_migration — Cost, price, bargaining power, margin and profit-allocation evidence are separately required.
- LEVEL-05: industry_conclusion != company_benefit — Company product, qualification, capacity, order, revenue and profit evidence are separately required.
- LEVEL-06: company_capability != stock_investment_value — Valuation, expectations, catalysts, risk and time-window evidence are separately required.

## 7. Stopping states

- bounded_by_public_evidence: Public evidence supports a lower cognition level but cannot support the next level.
- resolved: All atomic minimum sufficiency, independence, contradiction and denominator conditions are met for the stated cognition ceiling.
- stopped_due_to_redundancy: New candidates repeat existing evidence chains or no longer change the research state or ceiling.
- stopped_due_to_scope: Product generation, application, method, geography, period or denominator cannot be reconciled without redefining the question.
- stopped_due_to_structural_limit: Required internal yield, qualification, mix, process-window or qualified-output evidence is not independently public.

## 8. Governance

- Future acquisition authorized: False
- Stage A2 authorized: False
- Stage B authorized: False
- Company mapping authorized: False
- Bottleneck judgment authorized: False
- Value migration judgment authorized: False
