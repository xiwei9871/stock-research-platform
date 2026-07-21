# AI PCB Targeted Evidence Assessment Wave 1 v1

This report is a deterministic projection of the assessment artifact. Acquired evidence coverage is not ER sufficiency.

## ER status

### PCB-ER-A01: insufficient

- Independent evidence chains: 1
- Reason: Scoped OIF definitions are clear, but all evidence comes from one standards organization and lacks independent engineering interpretation.
- Remaining gaps: Independent engineering interpretation outside OIF.
- Next action: human_review_for_possible_wave_1b_design

### PCB-ER-A02: insufficient

- Independent evidence chains: 1
- Reason: Normative 112G definitions are usable, while 448G rate/frequency comparisons lack independent measurements and a unified denominator.
- Remaining gaps: Independent rate/reach measurements with a common denominator and disclosed de-embedding.
- Next action: human_review_for_possible_wave_1b_design

### PCB-ER-A03: open

- Independent evidence chains: 1
- Reason: OIF defines RTLR and identifies alternatives, but no independent comparative evidence ranks the alternatives.
- Remaining gaps: Independent comparison of equalization, retiming, cable and optical alternatives.
- Next action: human_review_for_possible_wave_1b_design

### PCB-ER-A04: insufficient

- Independent evidence chains: 1
- Reason: Only a single OIF standard definition is usable; independent de-embedding and coupon methodology is absent.
- Remaining gaps: Independent de-embedding, fixture and test-coupon methodology.
- Next action: human_review_for_possible_wave_1b_design

### PCB-ER-B01: insufficient

- Independent evidence chains: 1
- Reason: Only one usable Isola supplier chain exists, with no stated test method or cross-supplier denominator.
- Remaining gaps: Usable test-method metadata, second supplier and independent material test.
- Next action: human_review_for_possible_wave_1b_design

### PCB-ER-B02: insufficient

- Independent evidence chains: 2
- Reason: One supplier guide and one vendor-academic experiment support bounded statements, but provenance and independent replication remain incomplete.
- Remaining gaps: Original venue/date and independent replication under matched experimental conditions.
- Next action: human_review_for_possible_wave_1b_design

## Atomic claims

### [SUFFICIENT] W1-A01-C01

OIF CEI-112G-LR-PAM4 defines a 36-58 Gsym/s PAM4 point-to-point differential interface over PCB copper traces, permits cable substitution, and specifies a reach of up to 1000 mm of backplane and two connectors.

- ER / type: PCB-ER-A01 / fact
- Scope: CEI-112G-LR-PAM4 Clause 27 only
- Generation: OIF-CEI-05.3 / CEI-112G-LR-PAM4
- Rate / frequency: 36-58 Gsym/s PAM4 / rate-defined; no cross-standard frequency comparison
- Distance / topology: up to 1000 mm backplane and two connectors / point-to-point balanced differential; unidirectional
- Test method: normative interface and channel definition
- Denominator: one CEI-112G-LR-PAM4 lane/channel
- Stance: support
- Evidence chains: evidence_chain:oif-cei-05.3
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The normative clause directly states the scoped interface characteristics.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Independent engineering interpretation outside OIF.
- Maximum cognition: standard_interface_definition
- Evidence: evidence_artifact:69c8eeb0e78fa58323fc09e9 / normalized_document:8da679d8934c639b303024e3 / section 620 / hash 567e4a559685...

### [SUFFICIENT] W1-A01-C02

OIF CEI-112G-XSR-PAM4 defines an extra-short-reach 36-58 Gsym/s PAM4 point-to-point electrical interface.

- ER / type: PCB-ER-A01 / fact
- Scope: CEI-112G-XSR-PAM4 Clause 24 only
- Generation: OIF-CEI-05.3 / CEI-112G-XSR-PAM4
- Rate / frequency: 36-58 Gsym/s PAM4 / not independently assessed
- Distance / topology: extra-short-reach class; no physical-length generalization / point-to-point electrical
- Test method: normative interface definition
- Denominator: one CEI-112G-XSR-PAM4 interface
- Stance: support
- Evidence chains: evidence_chain:oif-cei-05.3
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The clause directly defines the scoped interface class.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: standard_interface_definition
- Evidence: evidence_artifact:69c8eeb0e78fa58323fc09e9 / normalized_document:8da679d8934c639b303024e3 / section 522 / hash 219ef4ef6a11...

### [SUFFICIENT] W1-A01-C03

The OIF 448G framework places same-PCBA chip-to-chip links through PCB trace or board cable with up to one connector in the MR application space.

- ER / type: PCB-ER-A01 / fact
- Scope: OIF 448G framework application taxonomy
- Generation: OIF-FD-CEI-448G-01.0
- Rate / frequency: 448G framework context / not a normative compliance value
- Distance / topology: same PCBA, daughter card or short mid-plane / chip-to-chip through PCB trace or board cable, up to one connector
- Test method: framework taxonomy, not measured compliance
- Denominator: one framework-defined MR application space
- Stance: support
- Evidence chains: evidence_chain:oif-cei-448g-framework
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The framework directly states this taxonomy; sufficiency is limited to what the framework says.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: framework_application_definition
- Evidence: evidence_artifact:4c00b05bf11e4dc7b47d36cb / normalized_document:3289c4bd4757cb5b6c747709 / section 40 / hash 266d2fa2bbfe...

### [SUFFICIENT] W1-A01-C04

The OIF 448G framework describes a traditional chip-to-module VSR link as host PCB trace, connector and module PCB trace, while noting cabled-host alternatives.

- ER / type: PCB-ER-A01 / fact
- Scope: OIF 448G framework chip-to-module discussion
- Generation: OIF-FD-CEI-448G-01.0
- Rate / frequency: higher-rate/448G framework context / not a normative compliance value
- Distance / topology: chip-to-module VSR application space / host PCB or cabled host to pluggable module
- Test method: framework architecture discussion
- Denominator: one framework-defined VSR application
- Stance: support
- Evidence chains: evidence_chain:oif-cei-448g-framework
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The architecture alternatives are directly stated in the framework.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: framework_application_definition
- Evidence: evidence_artifact:4c00b05bf11e4dc7b47d36cb / normalized_document:3289c4bd4757cb5b6c747709 / section 39 / hash 24e4d8fa170a...

### [SUFFICIENT] W1-A02-C01

Within CEI-112G-LR-PAM4, channel compliance is normative through COM, while the plotted insertion-loss limit is explicitly informative.

- ER / type: PCB-ER-A02 / fact
- Scope: CEI-112G-LR-PAM4 channel compliance only
- Generation: OIF-CEI-05.3 / CEI-112G-LR-PAM4
- Rate / frequency: 36-58 Gsym/s / 0.05 GHz through the clause-defined range
- Distance / topology: the Clause 27 LR channel / test points T-to-R
- Test method: COM per IEEE 802.3 procedure as modified by the cited clause; informative IL curve
- Denominator: one Clause 27 T-to-R channel at its specified baud rate
- Stance: support
- Evidence chains: evidence_chain:oif-cei-05.3
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The standard directly distinguishes the normative and informative metrics.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: single_standard_measurement_definition
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 622 / hash 813d4f1d494e...
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 625 / hash 27c88e21170a...

### [SUFFICIENT] W1-A02-C02

OIF CEI assigns different 112G XSR, MR and LR channel classes to different physical/application reaches, so measurements must retain the named class denominator.

- ER / type: PCB-ER-A02 / fact
- Scope: OIF CEI 112G reach-class definitions
- Generation: OIF-CEI-05.3
- Rate / frequency: 36-58 Gsym/s PAM4 / class-specific
- Distance / topology: XSR, MR and LR are separate scoped classes / class-specific point-to-point channels
- Test method: normative class definitions
- Denominator: one named CEI reach class; classes cannot be pooled
- Stance: support
- Evidence chains: evidence_chain:oif-cei-05.3
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The standard provides distinct class definitions; the claim does not compare performance across classes.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: standard_comparison_denominator
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 522 / hash 219ef4ef6a11...
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 600 / hash a4ee1596f024...
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 620 / hash 567e4a559685...

### [INSUFFICIENT] W1-A02-C03

The OIF 448G framework states that 448G-PAM4 implies 224 GBd and 112 GHz Nyquist and attributes an approximately 90 GHz channel-bandwidth limit largely to connector technology.

- ER / type: PCB-ER-A02 / inference
- Scope: OIF 448G framework scenario, not released IA
- Generation: OIF-FD-CEI-448G-01.0
- Rate / frequency: 448 Gb/s PAM4 / 224 GBd / 112 GHz Nyquist; cited ~90 GHz limit
- Distance / topology: BGA-to-BGA framework example / package/connector channel example
- Test method: framework calculation and cited figure; independent method not supplied in Wave 1
- Denominator: one 448G-PAM4 framework scenario
- Stance: support
- Evidence chains: evidence_chain:oif-cei-448g-framework
- Independence: single_primary_chain
- Freshness / confidence: unknown / low
- Assessment reason: The arithmetic and framework statement are visible, but the underlying connector dataset and independent measurement provenance are not established.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: Higher-order modulation changes the Nyquist denominator.; Equalization and connector architecture may alter the operational boundary.
- Missing evidence: Independent channel measurements with defined fixture, de-embedding and geometry.
- Maximum cognition: framework_hypothesis_only
- Evidence: evidence_artifact:3545a22276fe30d8dcb1440c / normalized_document:1f503b4ce9f191fdd7e225ca / section 30 / hash e3d3213ffb70...

### [OPEN] W1-A02-C04

The framework's reported 67/85/100/106 GHz connector operational limits are not yet comparable evidence of a general rate-distance relationship.

- ER / type: PCB-ER-A02 / judgment
- Scope: Figure 29 connector examples in OIF 448G framework
- Generation: OIF-FD-CEI-448G-01.0
- Rate / frequency: 448G framework / 67-106 GHz reported examples
- Distance / topology: connector/interconnect examples / OSFP/CPC examples
- Test method: figure-level SDD21 discussion; full setup and common denominator unavailable
- Denominator: unresolved across connector examples
- Stance: contextual
- Evidence chains: evidence_chain:oif-cei-448g-framework
- Independence: single_primary_chain
- Freshness / confidence: unknown / low
- Assessment reason: The normalized text reports limits but does not establish a common test setup, distance, geometry or independent data origin.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Original measurement records and a unified denominator.
- Maximum cognition: contextual_boundary_only
- Evidence: evidence_artifact:3545a22276fe30d8dcb1440c / normalized_document:1f503b4ce9f191fdd7e225ca / section 52 / hash 78700571eccc...
- Evidence: evidence_artifact:3545a22276fe30d8dcb1440c / normalized_document:1f503b4ce9f191fdd7e225ca / section 53 / hash a87267bff357...

### [SUFFICIENT] W1-A03-C01

OIF EEI-112G-RTLR specifies retimed/equalized egress and linear ingress for a 36-56 Gsym/s chip-to-module interface, with up to 16 dB ball-to-ball channel loss including one connector.

- ER / type: PCB-ER-A03 / fact
- Scope: OIF EEI-112G-RTLR only
- Generation: OIF-EEI-112G-RTLR-01.0
- Rate / frequency: 36-56 Gsym/s PAM4 / Nyquist-frequency loss budget in the cited agreement
- Distance / topology: chip-to-module channel / retimed transmitter egress, linear receiver ingress
- Test method: normative implementation agreement
- Denominator: one EEI-112G-RTLR chip-to-module lane
- Stance: support
- Evidence chains: evidence_chain:oif-rtlr-112g
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The agreement directly defines the scoped architecture.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: single_standard_architecture_definition
- Evidence: evidence_artifact:c65c0a4065ea826e834d838d / normalized_document:4b83f07ad106253dd795aeeb / section 3 / hash 48828d97a09e...
- Evidence: evidence_artifact:c65c0a4065ea826e834d838d / normalized_document:4b83f07ad106253dd795aeeb / section 8 / hash 39456fcf47fe...

### [SUFFICIENT] W1-A03-C02

The RTLR agreement permits cables to replace part of the PCB copper path and specifies at least 200 mm host PCB trace, one connector and 20 mm module PCB trace in its scoped requirement.

- ER / type: PCB-ER-A03 / fact
- Scope: OIF EEI-112G-RTLR requirement
- Generation: OIF-EEI-112G-RTLR-01.0
- Rate / frequency: 36-56 Gsym/s PAM4 / agreement-specific
- Distance / topology: 200 mm host PCB + connector + 20 mm module PCB minimum capability / host-to-module copper/cable channel
- Test method: normative requirement
- Denominator: one RTLR host-to-module channel
- Stance: support
- Evidence chains: evidence_chain:oif-rtlr-112g
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The requirement directly states the scoped physical path.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: single_standard_architecture_definition
- Evidence: evidence_artifact:c65c0a4065ea826e834d838d / normalized_document:4b83f07ad106253dd795aeeb / section 8 / hash 39456fcf47fe...

### [SUFFICIENT] W1-A03-C03

The OIF framework identifies direct-drive CPO as a possible way to reduce electrical connector/channel reach limitations, while explicitly leaving deployment readiness uncertain.

- ER / type: PCB-ER-A03 / fact
- Scope: OIF 448G future-framework discussion
- Generation: OIF-FD-CEI-448G-01.0
- Rate / frequency: 448G framework / framework scenario
- Distance / topology: scale-up/scale-out and CPO scenario / direct-drive co-packaged optics
- Test method: future-framework discussion, not comparative field evidence
- Denominator: one stated framework option
- Stance: support
- Evidence chains: evidence_chain:oif-cei-448g-framework
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The claim is limited to accurately reporting the framework's option and caveat.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: framework_route_option
- Evidence: evidence_artifact:64f3622e79337c21853fa4bd / normalized_document:91e431f42a1b1de42ec23ae9 / section 31 / hash dd31ba4ed8d6...

### [OPEN] W1-A03-C04

Wave 1 does not establish which combination of equalization, retiming, cable, advanced modulation, FEC or optical placement is superior outside the cited OIF application spaces.

- ER / type: PCB-ER-A03 / judgment
- Scope: Cross-route comparison beyond OIF definitions
- Generation: 112G RTLR and 448G framework
- Rate / frequency: 112G and 448G contexts are not pooled / route-specific
- Distance / topology: route-specific / multiple electrical/optical alternatives
- Test method: no independent comparative experiment in Wave 1
- Denominator: unresolved across routes
- Stance: contextual
- Evidence chains: evidence_chain:oif-cei-448g-framework
- Independence: single_primary_chain
- Freshness / confidence: unknown / low
- Assessment reason: Alternatives are identified, but comparative power, BER, latency, reach and cost evidence is absent.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Independent route-comparison measurements with matched scope and denominator.
- Maximum cognition: alternative_route_register
- Evidence: evidence_artifact:64f3622e79337c21853fa4bd / normalized_document:91e431f42a1b1de42ec23ae9 / section 39 / hash 24e4d8fa170a...
- Evidence: evidence_artifact:64f3622e79337c21853fa4bd / normalized_document:91e431f42a1b1de42ec23ae9 / section 40 / hash 266d2fa2bbfe...
- Evidence: evidence_artifact:64f3622e79337c21853fa4bd / normalized_document:91e431f42a1b1de42ec23ae9 / section 42 / hash b1134d2778be...

### [SUFFICIENT] W1-A04-C01

For CEI-112G-LR-PAM4, OIF defines the channel between test points T and R, computes normative COM with stated frequency/baud parameters, and labels the insertion-loss curve informative.

- ER / type: PCB-ER-A04 / fact
- Scope: OIF CEI-112G-LR-PAM4 only
- Generation: OIF-CEI-05.3 / Clause 27
- Rate / frequency: 36-58 Gsym/s / 0.05 GHz through clause-defined upper range
- Distance / topology: Clause 27 LR channel / T-to-R differential channel
- Test method: OIF/IEEE-derived COM; informative IL curve
- Denominator: one Clause 27 T-to-R channel
- Stance: support
- Evidence chains: evidence_chain:oif-cei-05.3
- Independence: single_primary_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The standard directly defines the scoped metric hierarchy.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: single_standard_definition_only
- Evidence: evidence_artifact:291792bb9ba603b04bd4382f / normalized_document:451442cedcaab779e04be686 / section 622 / hash 813d4f1d494e...
- Evidence: evidence_artifact:291792bb9ba603b04bd4382f / normalized_document:451442cedcaab779e04be686 / section 625 / hash 27c88e21170a...

### [NOT_ASSESSABLE] W1-A04-C02

Wave 1 does not contain usable independent evidence for de-embedding, fixture removal or test-coupon methodology.

- ER / type: PCB-ER-A04 / judgment
- Scope: Independent measurement methodology beyond OIF
- Generation: not established
- Rate / frequency: not established / not established
- Distance / topology: not established / not established
- Test method: missing
- Denominator: not_defined
- Stance: non_evidence
- Evidence chains: 
- Independence: single_primary_chain
- Freshness / confidence: unknown / low
- Assessment reason: The NIST candidate was blocked and no other normalized independent measurement-method document is available.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Independent measurement methodology covering fixtures, de-embedding and coupons.
- Maximum cognition: single_standard_definition_only

### [OPEN] W1-A04-C03

OIF's single-standard definitions cannot be treated as evidence of all industry insertion-loss measurement practice.

- ER / type: PCB-ER-A04 / judgment
- Scope: Industry-wide measurement practice
- Generation: not established
- Rate / frequency: not pooled / not pooled
- Distance / topology: not pooled / not pooled
- Test method: only one standard family available
- Denominator: industry practice denominator unresolved
- Stance: contextual
- Evidence chains: evidence_chain:oif-cei-05.3
- Independence: single_primary_chain
- Freshness / confidence: unknown / low
- Assessment reason: No independent standard, metrology paper or instrument-method source is usable in Wave 1.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Independent standards/metrology comparison.
- Maximum cognition: single_standard_definition_only
- Evidence: evidence_artifact:291792bb9ba603b04bd4382f / normalized_document:451442cedcaab779e04be686 / section 625 / hash 27c88e21170a...

### [SUFFICIENT] W1-B01-C01

Isola's I-Tera MT40 table declares construction-specific Dk and Df values at 2, 5, 10, 15 and 20 GHz together with resin content and thickness.

- ER / type: PCB-ER-B01 / fact
- Scope: I-Tera MT40 supplier table only
- Generation: I-Tera MT40 Revision L
- Rate / frequency: not specified / 2/5/10/15/20 GHz
- Distance / topology: not applicable / core and prepreg material constructions
- Test method: not stated in the normalized table
- Denominator: one listed I-Tera construction/resin-content/thickness row
- Stance: support
- Evidence chains: evidence_chain:isola-i-tera-dkdf
- Independence: single_supplier_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The table directly supports only the supplier-declared row values.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Test method, direction, environment and independent validation.
- Maximum cognition: supplier_specific_parameter_and_method_understanding
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 0 / hash 315e446c7817...
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 2 / hash 550127467b40...

### [SUFFICIENT] W1-B01-C02

Within the I-Tera table, declared Dk/Df values are indexed by glass construction, resin content and thickness, so row-level construction is part of the comparison denominator.

- ER / type: PCB-ER-B01 / fact
- Scope: I-Tera MT40 table structure
- Generation: I-Tera MT40 Revision L
- Rate / frequency: not specified / 2-20 GHz columns
- Distance / topology: not applicable / material constructions
- Test method: supplier table organization
- Denominator: same frequency and one specified construction/resin/thickness row
- Stance: support
- Evidence chains: evidence_chain:isola-i-tera-dkdf
- Independence: single_supplier_chain
- Freshness / confidence: unknown / medium
- Assessment reason: The table structure directly establishes the required row denominator; it does not establish causality.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: supplier_specific_parameter_and_method_understanding
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 0 / hash 315e446c7817...
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 2 / hash 550127467b40...

### [NOT_ASSESSABLE] W1-B01-C03

Wave 1 cannot determine the Dk/Df test method, directionality, humidity/temperature conditions or whether table values are nominal, typical or guaranteed.

- ER / type: PCB-ER-B01 / judgment
- Scope: I-Tera measurement-method interpretation
- Generation: I-Tera MT40 Revision L
- Rate / frequency: not applicable / 2-20 GHz
- Distance / topology: not applicable / material specimens
- Test method: not stated in usable normalized evidence
- Denominator: not_defined
- Stance: non_evidence
- Evidence chains: 
- Independence: single_primary_chain
- Freshness / confidence: unknown / low
- Assessment reason: The normalized table contains values and revision history but not the required method metadata; the additional Isola paper failed normalization.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Usable method document and independent test record.
- Maximum cognition: supplier_specific_parameter_and_method_understanding

### [INSUFFICIENT] W1-B01-C04

The acquired B01 evidence cannot support cross-supplier Dk/Df comparability or whole-channel performance.

- ER / type: PCB-ER-B01 / judgment
- Scope: Cross-supplier and board-level inference
- Generation: not established
- Rate / frequency: not established / not harmonized
- Distance / topology: not applicable / not applicable
- Test method: only one usable supplier chain
- Denominator: cross-supplier denominator unresolved
- Stance: contextual
- Evidence chains: evidence_chain:isola-i-tera-dkdf
- Independence: single_supplier_chain
- Freshness / confidence: unknown / low
- Assessment reason: Rogers acquisition failed, the second Isola PDF is encrypted, and no independent test source is usable.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Second supplier with harmonized method and independent material testing.
- Maximum cognition: supplier_specific_parameter_and_method_understanding
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 0 / hash 315e446c7817...

### [SUFFICIENT] W1-B02-C01

Isola's high-speed design guide states that rough copper increases resistance and that its electrical impact grows with data rate.

- ER / type: PCB-ER-B02 / fact
- Scope: Isola supplier guide statement
- Generation: supplier HSD guide
- Rate / frequency: qualitative higher-data-rate context / not tied to a complete test method
- Distance / topology: not specified / PCB conductor surfaces
- Test method: supplier presentation; method not shown for the quoted percentage
- Denominator: supplier-stated rough versus smoother conductor context
- Stance: support
- Evidence chains: evidence_chain:isola-hsd-guide
- Independence: supplier_primary_only
- Freshness / confidence: unknown / low
- Assessment reason: Sufficient only as a record of the supplier's scoped technical statement, not as independent quantitative proof.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Independent measurement matching the stated percentage.
- Maximum cognition: supplier_specific_roughness_context
- Evidence: evidence_artifact:6d6a80e65b045e0a9025c910 / normalized_document:0e3c7fd470c06f407d0d07a3 / section 15 / hash cda72304b3c4...
- Evidence: evidence_artifact:6d6a80e65b045e0a9025c910 / normalized_document:0e3c7fd470c06f407d0d07a3 / section 16 / hash dd78011ad631...

### [SUFFICIENT] W1-B02-C02

The Isola guide distinguishes RTF, LP and VLP foil profiles and reports example Rq values for RTF and VLP.

- ER / type: PCB-ER-B02 / fact
- Scope: Isola guide foil taxonomy
- Generation: supplier HSD guide
- Rate / frequency: not specified / not specified
- Distance / topology: not applicable / copper foil surfaces
- Test method: supplier presentation
- Denominator: the guide's named foil-profile examples
- Stance: support
- Evidence chains: evidence_chain:isola-hsd-guide
- Independence: supplier_primary_only
- Freshness / confidence: unknown / medium
- Assessment reason: The foil taxonomy and example values are directly stated.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: supplier_specific_roughness_context
- Evidence: evidence_artifact:6d6a80e65b045e0a9025c910 / normalized_document:0e3c7fd470c06f407d0d07a3 / section 17 / hash 01b87551c2e8...

### [SUFFICIENT] W1-B02-C03

The Mitsui/Shibaura paper describes four-layer evaluation boards with microstrip/stripline and differential/single-ended structures, three dielectrics, 100/200/300 mm lengths, and VNA S21/Sdd21 measurement from 300 kHz to 20 GHz.

- ER / type: PCB-ER-B02 / fact
- Scope: The cited evaluation-board experiment only
- Generation: paper's experimental setup
- Rate / frequency: not a protocol-rate test / 300 kHz-20 GHz
- Distance / topology: 100/200/300 mm; cited comparison at 200 mm / microstrip and stripline; single-ended and differential
- Test method: Agilent E5071C VNA S21/Sdd21 measurement
- Denominator: one stated geometry, dielectric, length and frequency
- Stance: support
- Evidence chains: evidence_chain:mitsui-shibaura-roughness-paper
- Independence: vendor_academic_joint_source
- Freshness / confidence: unknown / medium
- Assessment reason: The normalized paper text directly specifies the experimental denominator.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: 
- Maximum cognition: single_experiment_engineering_understanding
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 2 / hash 3c455f6f21e7...
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 3 / hash 3a90de9a2066...

### [SUFFICIENT] W1-B02-C04

In the paper's 200 mm G1 stripline experiment at 20 GHz, lower bonding-side Rz was associated with lower measured signal loss; NP-VSP was reported at about 17% lower total loss than RTF.

- ER / type: PCB-ER-B02 / fact
- Scope: One paper's G1 200 mm stripline comparison
- Generation: paper's copper-foil experiment
- Rate / frequency: not a protocol-rate test / 20 GHz
- Distance / topology: 200 mm / stripline in dielectric G1
- Test method: Rz/Rq by two non-contact profilometers and VNA loss measurement
- Denominator: same G1 dielectric, 200 mm stripline and 20 GHz comparison
- Stance: support
- Evidence chains: evidence_chain:mitsui-shibaura-roughness-paper
- Independence: vendor_academic_joint_source
- Freshness / confidence: unknown / medium
- Assessment reason: The experiment states geometry, material, frequency, roughness metric and measured relationship.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: Dielectric and conductor-loss separation depends on the paper's regression model.; Foil treatment and adhesion changes may covary with measured roughness.
- Missing evidence: 
- Maximum cognition: single_experiment_engineering_understanding
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 8 / hash 339e752c3251...
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 13 / hash 4f3528a6915a...
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 14 / hash 1598b680cf33...

### [OPEN] W1-B02-C05

The roughness paper's authors and affiliations are identifiable, but Wave 1 does not verify its original publication venue or publication date from normalized content.

- ER / type: PCB-ER-B02 / judgment
- Scope: Source provenance for the roughness paper
- Generation: unknown publication version
- Rate / frequency: not applicable / not applicable
- Distance / topology: not applicable / not applicable
- Test method: repository copy; original venue absent from normalized text
- Denominator: one document copy
- Stance: contextual
- Evidence chains: evidence_chain:mitsui-shibaura-roughness-paper
- Independence: vendor_academic_joint_source
- Freshness / confidence: unknown / low
- Assessment reason: The SMTnet-hosted PDF exposes authorship and institutions but not a confirmed original venue/date.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Original publisher/venue record and publication date.
- Maximum cognition: source_provenance_partially_verified
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 0 / hash bd666ff9c932...

### [INSUFFICIENT] W1-B02-C06

Wave 1 does not establish that the paper's roughness-loss result generalizes across suppliers, modern high-speed geometries, frequencies or production boards.

- ER / type: PCB-ER-B02 / judgment
- Scope: Industry-wide generalization
- Generation: not established
- Rate / frequency: not established / beyond 20 GHz not established
- Distance / topology: beyond cited lengths not established / beyond cited structures not established
- Test method: one supplier guide and one vendor-academic experiment
- Denominator: industry denominator unresolved
- Stance: mixed
- Evidence chains: evidence_chain:mitsui-shibaura-roughness-paper; evidence_chain:isola-hsd-guide
- Independence: partially_independent_but_not_replication
- Freshness / confidence: unknown / low
- Assessment reason: The two chains are distinct but neither provides independent replication across a harmonized production denominator.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Counterevidence: 
- Alternative explanations: 
- Missing evidence: Independent replication with matched geometry, material, roughness metric and frequency.
- Maximum cognition: bounded_experimental_relationship
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 13 / hash 4f3528a6915a...
- Evidence: evidence_artifact:6d6a80e65b045e0a9025c910 / normalized_document:0e3c7fd470c06f407d0d07a3 / section 32 / hash aa059135a86f...

## Excluded records

- acquisition_attempt:0fb51bcc55929ef2b6212f18: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:18a4136f61de15dbdbebe7b1: blocked records cannot be claim evidence.
- acquisition_attempt:21e98e3c46853785bde2dde1: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:36213f4e02997eff495fe0ee: failed records cannot be claim evidence.
- acquisition_attempt:3913420533560cbb0805c58c: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:3fe303b0aa0b800642c7f9e7: failed records cannot be claim evidence.
- acquisition_attempt:437f6e2be6b03f0b88f118f4: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:59eb9d671cbf2b1b4a709a3c: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:5c15b444e76178c7131a6196: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:5e1b374c1779aaeb62fbeed8: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:5e204e0c42c97b439eb263a6: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:75e7cb3505a8a018e8de0145: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:8e1cf19a5427152973c4f0a5: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:92bbd27c1b0f3e59f5596cd7: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:aee44f9311d564fe663e7211: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:b4d9adde572138afbae09be6: blocked records cannot be claim evidence.
- acquisition_attempt:b75a616b03a58c13a438c57d: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:dc0f37553255189c2bfedef9: blocked records cannot be claim evidence.
- acquisition_attempt:ec3ba29adaf08830ca2d25bc: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:f2aadb665e22f662efd48717: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:f804f3d18490cf759f3e591f: Engineering preflight attempt has zero evidence coverage.
- evidence_artifact:7a83297ace04a613f69e6f02: Encrypted or normalization-failed raw artifact has no usable normalized-text locator.
