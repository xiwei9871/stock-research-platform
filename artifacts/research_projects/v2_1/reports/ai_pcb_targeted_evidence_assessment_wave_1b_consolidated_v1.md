# AI PCB Targeted Evidence Assessment Wave 1b Consolidated v1

This report is a deterministic projection of the consolidated assessment artifact. Evidence acquisition volume is not evidence sufficiency.

## Consolidated answer

- Understood: OIF-specific insertion-loss and COM definitions; a limited NIST metrology baseline for insertion loss, two-line subtraction and TRL reference-plane calibration; Isola-specific Dk/Df declarations and the conditions visible in its table; one bounded copper-roughness experiment; one IEEE P802.3ck channel-set and COM equalizer experiment
- Scope-limited understanding: A04 is limited to OIF plus an older NIST metrology baseline, not current production coupon practice; B01 remains supplier-specific despite independent method context; B02 remains one experiment without verified publication provenance or replication; A02 is multi-organization but not a harmonized rate-distance comparison
- Machine public-acquisition ceiling: B01 method mapping and second-supplier comparability; B02 publication identity and independent replication; A04 current fixture-removal and coupon applicability; A02 cross-standard denominator reconciliation
- Manual evidence candidates: B02 publication identity; B01 formal method and second supplier; A04 current full-text de-embedding/coupon method; A02 expert denominator review
- Stop-investment items: Panasonic same-entry retry without a new exact identifier; additional automated Recovery using the exhausted five targets

## ER status

### PCB-ER-A04: insufficient

- Independent evidence chains: 2
- Reason: NIST adds an independent, dated metrology chain for insertion-loss and reference-plane calibration, but modern fixture-removal and coupon-to-channel applicability remain unsupported.
- Remaining gaps: Current full-text fixture-removal and coupon-to-channel methodology.
- Next action: manual_source_resolution_for_current_deembedding_and_coupon_method

### PCB-ER-B01: insufficient

- Independent evidence chains: 2
- Reason: NIST establishes why method and specimen conditions constrain comparison, while the material values remain one Isola supplier chain without a verified method or matched second supplier.
- Remaining gaps: Verified supplier test method, denominator-matched second supplier, and independent current measurement.
- Next action: manual_source_resolution_for_test_method_and_second_supplier

### PCB-ER-B02: insufficient

- Independent evidence chains: 2
- Reason: Wave 1 still supports only one bounded roughness experiment plus supplier context; Recovery added no identity-matched B02 evidence.
- Remaining gaps: Original publication identity/date and independent matched replication.
- Next action: manual_publication_identity_resolution_then_stop_or_reassess

### PCB-ER-A02: insufficient

- Independent evidence chains: 2
- Reason: The IEEE contribution adds an independent bounded channel/COM experiment, but rate, reach, topology, reference plane and de-embedding remain non-comparable with OIF evidence.
- Remaining gaps: Cross-standard rate/reach comparison with harmonized channel composition and de-embedding.
- Next action: expert_denominator_review_before_any_additional_source_work

## Atomic claims

### [SUFFICIENT] CON-A02-C05

One IEEE P802.3ck contribution analyzes 107 repository channels, selects a highlighted subset below 29 dB insertion loss, and reports the subset insertion-loss distribution.

- ER / type: PCB-ER-A02 / fact
- Scope: IEEE P802.3ck May 2019 backplane COM contribution
- Denominator: 107 repository channels; highlighted subset below 29 dB insertion loss
- Evidence chains: evidence_chain:ieee-802-3ck-backplane-com-2019
- Freshness / confidence: unknown / medium
- Assessment reason: The contribution directly documents this bounded channel-set analysis.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.; The slides do not provide a harmonized physical length, topology composition or de-embedding denominator for cross-standard comparison.
- Missing evidence: 
- Maximum cognition: single_working_group_measurement_set
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 4 / hash 0fb6d32c8239...
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 5 / hash d1c927bf3954...
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 6 / hash 6d8c2f7509d3...
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 7 / hash 9039bd7738c8...

### [SUFFICIENT] CON-A02-C06

Within that IEEE contribution, COM pass rates vary with equalizer assumptions including transmitter taps, floating-tap span, device capacitance and post-cursor settings; insertion loss alone does not determine the reported COM outcome.

- ER / type: PCB-ER-A02 / fact
- Scope: IEEE P802.3ck contribution's stated COM experiment
- Denominator: the contribution's fixed channel set and COM model configuration
- Evidence chains: evidence_chain:ieee-802-3ck-backplane-com-2019
- Freshness / confidence: unknown / medium
- Assessment reason: The experiment directly varies equalizer/model parameters and reports different outcomes.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: 
- Maximum cognition: single_working_group_measurement_set
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 10 / hash 7d6cc9ca8d14...
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 11 / hash f13a9cb53cdb...
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 12 / hash 35562b9f964e...

### [INSUFFICIENT] CON-A02-C07

Combining OIF and IEEE evidence still does not establish a general rate-distance relationship because rate, Nyquist frequency, physical reach, channel composition, reference plane and de-embedding are not harmonized across the two evidence chains.

- ER / type: PCB-ER-A02 / judgment
- Scope: Cross-standard rate, reach and channel-metric comparison
- Denominator: cross-standard denominator unresolved
- Evidence chains: evidence_chain:oif-cei-05.3; evidence_chain:ieee-802-3ck-backplane-com-2019
- Freshness / confidence: unknown / low
- Assessment reason: The new chain adds a bounded experiment but not the common denominator required for general comparison.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: A harmonized comparison with explicit rate, Nyquist frequency, reach, topology, reference plane and de-embedding.
- Maximum cognition: multi_standard_limited_metric_understanding
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 4 / hash 0fb6d32c8239...
- Evidence: evidence_artifact:5cf8a72e4f4c6a9043a474c5 / normalized_document:019803185d3da18b4d1f2486 / section 10 / hash 7d6cc9ca8d14...
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 622 / hash 813d4f1d494e...

### [SUFFICIENT] CON-A04-C02

NIST Technical Note 1520 defines insertion loss and describes a two-line-length method that subtracts common calibration and sample-holder mismatch when those effects are equivalent between measurements.

- ER / type: PCB-ER-A04 / fact
- Scope: NIST Technical Note 1520 conductor-loss measurement discussion
- Denominator: two line lengths with equivalent calibration and sample-holder mismatch
- Evidence chains: evidence_chain:nist-tn-1520
- Freshness / confidence: stale / medium
- Assessment reason: The technical note directly defines the scoped method and its matching assumption.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.; The 2001 method discussion is not evidence that all current high-speed fixtures or production coupons use the same implementation.
- Missing evidence: 
- Maximum cognition: limited_metrology_method_understanding
- Evidence: evidence_artifact:92ca57b518be8af5cb15e31d / normalized_document:fd60b1b4e815747495188397 / section 63 / hash 15bc0490739a...
- Evidence: evidence_artifact:92ca57b518be8af5cb15e31d / normalized_document:fd60b1b4e815747495188397 / section 64 / hash 308440c67f27...

### [SUFFICIENT] CON-A04-C03

NIST states that reference-plane calibration for patterned structures can use TRL algorithms with transmission lines of varying lengths plus short and open structures.

- ER / type: PCB-ER-A04 / fact
- Scope: NIST patterned-structure reference-plane calibration discussion
- Denominator: one stated TRL calibration structure set
- Evidence chains: evidence_chain:nist-tn-1520
- Freshness / confidence: stale / medium
- Assessment reason: The reference-plane calibration method is directly described.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.; This does not establish a complete modern fixture-removal or IEEE 370 compliance workflow.
- Missing evidence: 
- Maximum cognition: limited_metrology_method_understanding
- Evidence: evidence_artifact:92ca57b518be8af5cb15e31d / normalized_document:fd60b1b4e815747495188397 / section 58 / hash 871e2f72c564...

### [INSUFFICIENT] CON-A04-C04

The consolidated evidence does not establish how a production test coupon maps to an actual high-speed channel, nor the applicability limits of modern fixture-removal and de-embedding implementations.

- ER / type: PCB-ER-A04 / judgment
- Scope: Modern production coupon and fixture-removal practice
- Denominator: modern coupon, fixture and actual-channel denominator unresolved
- Evidence chains: evidence_chain:nist-tn-1520
- Freshness / confidence: stale / low
- Assessment reason: A limited metrology baseline exists, but the requested modern coupon and fixture boundary remains unsupported.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Current full-text de-embedding/fixture method and auditable coupon-to-channel validation.
- Maximum cognition: limited_metrology_method_understanding
- Evidence: evidence_artifact:92ca57b518be8af5cb15e31d / normalized_document:fd60b1b4e815747495188397 / section 58 / hash 871e2f72c564...
- Evidence: evidence_artifact:92ca57b518be8af5cb15e31d / normalized_document:fd60b1b4e815747495188397 / section 136 / hash 6bf7195a0785...

### [SUFFICIENT] CON-B01-C03

NIST states that dielectric properties depend on frequency, anisotropy, temperature and other specimen conditions, and that no single measurement technique characterizes all materials across all frequencies and temperatures.

- ER / type: PCB-ER-B01 / fact
- Scope: NIST dielectric-measurement method limits
- Denominator: one method, specimen construction and stated environmental condition at a time
- Evidence chains: evidence_chain:nist-tn-1520
- Freshness / confidence: stale / medium
- Assessment reason: The source directly supports a scoped measurement-comparability boundary.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.; The source does not identify the method used for the acquired Isola table or provide a second supplier comparison.
- Missing evidence: 
- Maximum cognition: general_method_comparability_context
- Evidence: evidence_artifact:7305a7ff435cc1e69d72485f / normalized_document:c9b935aa14bdf30fe3c8a640 / section 22 / hash 6a8ed732b9f8...
- Evidence: evidence_artifact:7305a7ff435cc1e69d72485f / normalized_document:c9b935aa14bdf30fe3c8a640 / section 136 / hash 6bf7195a0785...

### [INSUFFICIENT] CON-B01-C05

The consolidated evidence cannot map the acquired Isola Dk/Df declarations to a verified test method, uncertainty statement or a denominator matched to another supplier.

- ER / type: PCB-ER-B01 / judgment
- Scope: Cross-source comparison of the Isola table
- Denominator: cross-supplier method, specimen and condition denominator unresolved
- Evidence chains: evidence_chain:isola-i-tera-dkdf; evidence_chain:nist-tn-1520
- Freshness / confidence: mixed / low
- Assessment reason: An independent method framework exists, but it cannot be linked to the supplier declaration denominator.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Formal method for the Isola values, a denominator-matched second supplier, and independent modern material measurement.
- Maximum cognition: supplier_specific_parameter_plus_method_boundary
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 0 / hash 315e446c7817...
- Evidence: evidence_artifact:7305a7ff435cc1e69d72485f / normalized_document:c9b935aa14bdf30fe3c8a640 / section 22 / hash 6a8ed732b9f8...

### [SUFFICIENT] W1-A02-C01

Within CEI-112G-LR-PAM4, channel compliance is normative through COM, while the plotted insertion-loss limit is explicitly informative.

- ER / type: PCB-ER-A02 / fact
- Scope: CEI-112G-LR-PAM4 channel compliance only
- Denominator: one Clause 27 T-to-R channel at its specified baud rate
- Evidence chains: evidence_chain:oif-cei-05.3
- Freshness / confidence: unknown / medium
- Assessment reason: The standard directly distinguishes the normative and informative metrics.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: 
- Maximum cognition: single_standard_measurement_definition
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 622 / hash 813d4f1d494e...
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 625 / hash 27c88e21170a...

### [SUFFICIENT] W1-A02-C02

OIF CEI assigns different 112G XSR, MR and LR channel classes to different physical/application reaches, so measurements must retain the named class denominator.

- ER / type: PCB-ER-A02 / fact
- Scope: OIF CEI 112G reach-class definitions
- Denominator: one named CEI reach class; classes cannot be pooled
- Evidence chains: evidence_chain:oif-cei-05.3
- Freshness / confidence: unknown / medium
- Assessment reason: The standard provides distinct class definitions; the claim does not compare performance across classes.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: 
- Maximum cognition: standard_comparison_denominator
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 522 / hash 219ef4ef6a11...
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 600 / hash a4ee1596f024...
- Evidence: evidence_artifact:eef74cc4d075e6b996599fc3 / normalized_document:8071e914d22caaed45914cac / section 620 / hash 567e4a559685...

### [INSUFFICIENT] W1-A02-C03

The OIF 448G framework states that 448G-PAM4 implies 224 GBd and 112 GHz Nyquist and attributes an approximately 90 GHz channel-bandwidth limit largely to connector technology.

- ER / type: PCB-ER-A02 / inference
- Scope: OIF 448G framework scenario, not released IA
- Denominator: one 448G-PAM4 framework scenario
- Evidence chains: evidence_chain:oif-cei-448g-framework
- Freshness / confidence: unknown / low
- Assessment reason: The arithmetic and framework statement are visible, but the underlying connector dataset and independent measurement provenance are not established.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Independent channel measurements with defined fixture, de-embedding and geometry.
- Maximum cognition: framework_hypothesis_only
- Evidence: evidence_artifact:3545a22276fe30d8dcb1440c / normalized_document:1f503b4ce9f191fdd7e225ca / section 30 / hash e3d3213ffb70...

### [OPEN] W1-A02-C04

The framework's reported 67/85/100/106 GHz connector operational limits are not yet comparable evidence of a general rate-distance relationship.

- ER / type: PCB-ER-A02 / judgment
- Scope: Figure 29 connector examples in OIF 448G framework
- Denominator: unresolved across connector examples
- Evidence chains: evidence_chain:oif-cei-448g-framework
- Freshness / confidence: unknown / low
- Assessment reason: The normalized text reports limits but does not establish a common test setup, distance, geometry or independent data origin.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Original measurement records and a unified denominator.
- Maximum cognition: contextual_boundary_only
- Evidence: evidence_artifact:3545a22276fe30d8dcb1440c / normalized_document:1f503b4ce9f191fdd7e225ca / section 52 / hash 78700571eccc...
- Evidence: evidence_artifact:3545a22276fe30d8dcb1440c / normalized_document:1f503b4ce9f191fdd7e225ca / section 53 / hash a87267bff357...

### [SUFFICIENT] W1-A04-C01

For CEI-112G-LR-PAM4, OIF defines the channel between test points T and R, computes normative COM with stated frequency/baud parameters, and labels the insertion-loss curve informative.

- ER / type: PCB-ER-A04 / fact
- Scope: OIF CEI-112G-LR-PAM4 only
- Denominator: one Clause 27 T-to-R channel
- Evidence chains: evidence_chain:oif-cei-05.3
- Freshness / confidence: unknown / medium
- Assessment reason: The standard directly defines the scoped metric hierarchy.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: 
- Maximum cognition: single_standard_definition_only
- Evidence: evidence_artifact:291792bb9ba603b04bd4382f / normalized_document:451442cedcaab779e04be686 / section 622 / hash 813d4f1d494e...
- Evidence: evidence_artifact:291792bb9ba603b04bd4382f / normalized_document:451442cedcaab779e04be686 / section 625 / hash 27c88e21170a...

### [OPEN] W1-A04-C03

OIF's single-standard definitions cannot be treated as evidence of all industry insertion-loss measurement practice.

- ER / type: PCB-ER-A04 / judgment
- Scope: Industry-wide measurement practice
- Denominator: industry practice denominator unresolved
- Evidence chains: evidence_chain:oif-cei-05.3
- Freshness / confidence: unknown / low
- Assessment reason: No independent standard, metrology paper or instrument-method source is usable in Wave 1.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Independent standards/metrology comparison.
- Maximum cognition: single_standard_definition_only
- Evidence: evidence_artifact:291792bb9ba603b04bd4382f / normalized_document:451442cedcaab779e04be686 / section 625 / hash 27c88e21170a...

### [SUFFICIENT] W1-B01-C01

Isola's I-Tera MT40 table declares construction-specific Dk and Df values at 2, 5, 10, 15 and 20 GHz together with resin content and thickness.

- ER / type: PCB-ER-B01 / fact
- Scope: I-Tera MT40 supplier table only
- Denominator: one listed I-Tera construction/resin-content/thickness row
- Evidence chains: evidence_chain:isola-i-tera-dkdf
- Freshness / confidence: unknown / medium
- Assessment reason: The table directly supports only the supplier-declared row values.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Test method, direction, environment and independent validation.
- Maximum cognition: supplier_specific_parameter_and_method_understanding
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 0 / hash 315e446c7817...
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 2 / hash 550127467b40...

### [SUFFICIENT] W1-B01-C02

Within the I-Tera table, declared Dk/Df values are indexed by glass construction, resin content and thickness, so row-level construction is part of the comparison denominator.

- ER / type: PCB-ER-B01 / fact
- Scope: I-Tera MT40 table structure
- Denominator: same frequency and one specified construction/resin/thickness row
- Evidence chains: evidence_chain:isola-i-tera-dkdf
- Freshness / confidence: unknown / medium
- Assessment reason: The table structure directly establishes the required row denominator; it does not establish causality.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: 
- Maximum cognition: supplier_specific_parameter_and_method_understanding
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 0 / hash 315e446c7817...
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 2 / hash 550127467b40...

### [INSUFFICIENT] W1-B01-C04

The acquired B01 evidence cannot support cross-supplier Dk/Df comparability or whole-channel performance.

- ER / type: PCB-ER-B01 / judgment
- Scope: Cross-supplier and board-level inference
- Denominator: cross-supplier denominator unresolved
- Evidence chains: evidence_chain:isola-i-tera-dkdf
- Freshness / confidence: unknown / low
- Assessment reason: Rogers acquisition failed, the second Isola PDF is encrypted, and no independent test source is usable.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Second supplier with harmonized method and independent material testing.
- Maximum cognition: supplier_specific_parameter_and_method_understanding
- Evidence: evidence_artifact:6e7d5f108e1ac7833d41b219 / normalized_document:f5daf52f0ba2e511f6f7f90c / section 0 / hash 315e446c7817...

### [SUFFICIENT] W1-B02-C01

Isola's high-speed design guide states that rough copper increases resistance and that its electrical impact grows with data rate.

- ER / type: PCB-ER-B02 / fact
- Scope: Isola supplier guide statement
- Denominator: supplier-stated rough versus smoother conductor context
- Evidence chains: evidence_chain:isola-hsd-guide
- Freshness / confidence: unknown / low
- Assessment reason: Sufficient only as a record of the supplier's scoped technical statement, not as independent quantitative proof.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Independent measurement matching the stated percentage.
- Maximum cognition: supplier_specific_roughness_context
- Evidence: evidence_artifact:6d6a80e65b045e0a9025c910 / normalized_document:0e3c7fd470c06f407d0d07a3 / section 15 / hash cda72304b3c4...
- Evidence: evidence_artifact:6d6a80e65b045e0a9025c910 / normalized_document:0e3c7fd470c06f407d0d07a3 / section 16 / hash dd78011ad631...

### [SUFFICIENT] W1-B02-C02

The Isola guide distinguishes RTF, LP and VLP foil profiles and reports example Rq values for RTF and VLP.

- ER / type: PCB-ER-B02 / fact
- Scope: Isola guide foil taxonomy
- Denominator: the guide's named foil-profile examples
- Evidence chains: evidence_chain:isola-hsd-guide
- Freshness / confidence: unknown / medium
- Assessment reason: The foil taxonomy and example values are directly stated.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: 
- Maximum cognition: supplier_specific_roughness_context
- Evidence: evidence_artifact:6d6a80e65b045e0a9025c910 / normalized_document:0e3c7fd470c06f407d0d07a3 / section 17 / hash 01b87551c2e8...

### [SUFFICIENT] W1-B02-C03

The Mitsui/Shibaura paper describes four-layer evaluation boards with microstrip/stripline and differential/single-ended structures, three dielectrics, 100/200/300 mm lengths, and VNA S21/Sdd21 measurement from 300 kHz to 20 GHz.

- ER / type: PCB-ER-B02 / fact
- Scope: The cited evaluation-board experiment only
- Denominator: one stated geometry, dielectric, length and frequency
- Evidence chains: evidence_chain:mitsui-shibaura-roughness-paper
- Freshness / confidence: unknown / medium
- Assessment reason: The normalized paper text directly specifies the experimental denominator.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: 
- Maximum cognition: single_experiment_engineering_understanding
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 2 / hash 3c455f6f21e7...
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 3 / hash 3a90de9a2066...

### [SUFFICIENT] W1-B02-C04

In the paper's 200 mm G1 stripline experiment at 20 GHz, lower bonding-side Rz was associated with lower measured signal loss; NP-VSP was reported at about 17% lower total loss than RTF.

- ER / type: PCB-ER-B02 / fact
- Scope: One paper's G1 200 mm stripline comparison
- Denominator: same G1 dielectric, 200 mm stripline and 20 GHz comparison
- Evidence chains: evidence_chain:mitsui-shibaura-roughness-paper
- Freshness / confidence: unknown / medium
- Assessment reason: The experiment states geometry, material, frequency, roughness metric and measured relationship.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: 
- Maximum cognition: single_experiment_engineering_understanding
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 8 / hash 339e752c3251...
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 13 / hash 4f3528a6915a...
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 14 / hash 1598b680cf33...

### [OPEN] W1-B02-C05

The roughness paper's authors and affiliations are identifiable, but Wave 1 does not verify its original publication venue or publication date from normalized content.

- ER / type: PCB-ER-B02 / judgment
- Scope: Source provenance for the roughness paper
- Denominator: one document copy
- Evidence chains: evidence_chain:mitsui-shibaura-roughness-paper
- Freshness / confidence: unknown / low
- Assessment reason: The SMTnet-hosted PDF exposes authorship and institutions but not a confirmed original venue/date.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Original publisher/venue record and publication date.
- Maximum cognition: source_provenance_partially_verified
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 0 / hash bd666ff9c932...

### [INSUFFICIENT] W1-B02-C06

Wave 1 does not establish that the paper's roughness-loss result generalizes across suppliers, modern high-speed geometries, frequencies or production boards.

- ER / type: PCB-ER-B02 / judgment
- Scope: Industry-wide generalization
- Denominator: industry denominator unresolved
- Evidence chains: evidence_chain:mitsui-shibaura-roughness-paper; evidence_chain:isola-hsd-guide
- Freshness / confidence: unknown / low
- Assessment reason: The two chains are distinct but neither provides independent replication across a harmonized production denominator.
- Limitations: The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure.
- Missing evidence: Independent replication with matched geometry, material, roughness metric and frequency.
- Maximum cognition: bounded_experimental_relationship
- Evidence: evidence_artifact:11d564e0e47f4118abc6d0c1 / normalized_document:72b1be30c0a4d52262534438 / section 13 / hash 4f3528a6915a...
- Evidence: evidence_artifact:6d6a80e65b045e0a9025c910 / normalized_document:0e3c7fd470c06f407d0d07a3 / section 32 / hash aa059135a86f...

## Unresolved evidence targets

### P0 manual_target:B02_publication_identity

- ER: PCB-ER-B02
- Classification: manual_source_resolution_candidate
- Why unresolved: The paper title, authors and affiliations are visible, but original venue, stable identifier and formal date remain unverified.
- Required human action: Confirm publisher or conference record, DOI or stable identifier, and explicit publication date without changing the technical evidence chain.
- Stop condition: Stop after one authoritative identity record is found or authoritative records cannot confirm the publication identity.
- Future action authorized: false

### P0 manual_target:B01_test_method_and_second_supplier

- ER: PCB-ER-B01
- Classification: manual_source_resolution_candidate
- Why unresolved: The Isola declarations lack a verified method mapping and no denominator-matched second supplier is available.
- Required human action: Resolve one formal Dk/Df method or equivalent method record and one second-supplier declaration with explicit frequency, specimen and value-status fields.
- Stop condition: Stop if only purchase pages, method-free datasheets or non-comparable specimen conditions are available.
- Future action authorized: false

### P1 manual_target:A04_modern_deembedding_coupon_method

- ER: PCB-ER-A04
- Classification: manual_source_resolution_candidate
- Why unresolved: NIST provides a limited calibration baseline but not a current full-text fixture-removal and coupon-to-channel method.
- Required human action: Resolve one current authoritative full-text method for de-embedding, fixture removal and coupon applicability, ideally Keysight, Anritsu or an equivalent standard source.
- Stop condition: Stop if available material remains overview-only or cannot state reference plane, fixture and applicability limits.
- Future action authorized: false

### P1 expert_target:A02_cross_standard_denominator

- ER: PCB-ER-A02
- Classification: expert_technical_review_candidate
- Why unresolved: OIF and IEEE evidence use different channel sets, assumptions and metric denominators.
- Required human action: A signal-integrity reviewer should decide whether any current OIF and IEEE metrics are legitimately comparable and specify the minimum shared denominator.
- Stop condition: Stop if rate, frequency, reach, topology, reference plane and equalization cannot be aligned without new primary measurements.
- Future action authorized: false

### P2 stop_target:Panasonic_same_entry

- ER: PCB-ER-B01
- Classification: stop_investment_recommended
- Why unresolved: The authorized bounded retry timed out and no new identifier or access path exists.
- Required human action: None unless a new exact official document identifier or legal stable entry is supplied externally.
- Stop condition: Do not retry the same entry under the current evidence plan.
- Future action authorized: false

## Excluded records

- acquisition_attempt:0a2a9b2db5759ecc96620196: Failed or manually unavailable recovery target cannot be claim evidence.
- acquisition_attempt:0fb51bcc55929ef2b6212f18: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:137cd149a7aeb9d86c42b324: failed Wave 1b records cannot be claim evidence.
- acquisition_attempt:149ff4578e04bf54ed3e8ec9: failed Wave 1b records cannot be claim evidence.
- acquisition_attempt:18a4136f61de15dbdbebe7b1: blocked records cannot be claim evidence.
- acquisition_attempt:1dbaef828ed6a4250b5444ea: Failed or manually unavailable recovery target cannot be claim evidence.
- acquisition_attempt:21e98e3c46853785bde2dde1: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:36213f4e02997eff495fe0ee: failed records cannot be claim evidence.
- acquisition_attempt:3913420533560cbb0805c58c: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:3ac716cb04119fa6605d64b8: blocked Wave 1b records cannot be claim evidence.
- acquisition_attempt:3fe303b0aa0b800642c7f9e7: failed records cannot be claim evidence.
- acquisition_attempt:437f6e2be6b03f0b88f118f4: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:59eb9d671cbf2b1b4a709a3c: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:5c15b444e76178c7131a6196: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:5e1b374c1779aaeb62fbeed8: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:5e204e0c42c97b439eb263a6: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:650278041f49295aff0f43a3: blocked Wave 1b records cannot be claim evidence.
- acquisition_attempt:75e7cb3505a8a018e8de0145: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:899884ee09e27f5b7663de34: failed Wave 1b records cannot be claim evidence.
- acquisition_attempt:8e1cf19a5427152973c4f0a5: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:91900fa73a686fbbb92f18da: blocked Wave 1b records cannot be claim evidence.
- acquisition_attempt:92bbd27c1b0f3e59f5596cd7: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:931ffda7526902ab289ca9a2: Failed or manually unavailable recovery target cannot be claim evidence.
- acquisition_attempt:99f81cf90db76e5a718ed8ff: Failed or manually unavailable recovery target cannot be claim evidence.
- acquisition_attempt:9ba8d53244f274d9c4f0932a: failed Wave 1b records cannot be claim evidence.
- acquisition_attempt:a547e1269d9d474018400097: blocked Wave 1b records cannot be claim evidence.
- acquisition_attempt:a57478220b336e2b12e73028: Failed or manually unavailable recovery target cannot be claim evidence.
- acquisition_attempt:aee44f9311d564fe663e7211: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:b4d9adde572138afbae09be6: blocked records cannot be claim evidence.
- acquisition_attempt:b75a616b03a58c13a438c57d: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:d3230c426bbc63aa6b627fd6: failed Wave 1b records cannot be claim evidence.
- acquisition_attempt:dc0f37553255189c2bfedef9: blocked records cannot be claim evidence.
- acquisition_attempt:dc11025130d93127dd3192a7: failed Wave 1b records cannot be claim evidence.
- acquisition_attempt:e4cbeff3c410a1218f869b86: failed Wave 1b records cannot be claim evidence.
- acquisition_attempt:ec3ba29adaf08830ca2d25bc: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:f2aadb665e22f662efd48717: Engineering preflight attempt has zero evidence coverage.
- acquisition_attempt:f804f3d18490cf759f3e591f: Engineering preflight attempt has zero evidence coverage.
- acquisition_capability_validation_only: Capability-hardening diagnostics and benchmark artifacts are not research evidence.
- evidence_artifact:0d692e4fad8a60be4244af2c: The IEEE index is discovery-only and cannot be claim evidence.
- evidence_artifact:24cebdac88b8cd9fc13c162d: The PCI-SIG overview is contextual and is not channel-measurement evidence.
- evidence_artifact:6afe3531d76f867d0a8620aa: The NIST document is not an independent replication of the B02 copper-roughness experiment.
- evidence_artifact:7a83297ace04a613f69e6f02: Encrypted or normalization-failed raw artifact has no usable normalized-text locator.
- evidence_artifact:8be4a0df1a729993d56f5088: The IEEE landing page is not the IEEE 370 full standard and resolved to a mismatched identity.
- evidence_artifact:a906a111c3b689ac19c58f3a: The acquired USC content does not match the frozen B02 target identity.
- normalized_document:500ae7dcaae88360df0e9c72: Equivalent resume output does not increase locator independence or evidence-chain count.
- normalized_document:c3ff111a56925e8c6836494f: Equivalent resume output does not increase locator independence or evidence-chain count.
