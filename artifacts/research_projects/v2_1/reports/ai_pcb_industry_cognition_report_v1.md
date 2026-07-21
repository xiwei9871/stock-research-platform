# AI PCB 研究认知基线 v1：AI 系统互连需求侧证据与 PCB 技术缺口

## 1. 研究问题与边界

- Topic: AI compute interconnect and PCB cognition baseline
- Objective: Determine what the existing Stage A evidence supports about AI-system interconnect and where PCB technical cognition remains absent.
- Model scope: demand_side_and_system_interconnect
- Included: AI accelerator-system architecture; scale-up and scale-out roles; network fabric; DPU/NIC boundary; switch throughput context; optical-interconnect boundary claims
- Excluded: PCB manufacturing conclusions; company mapping; stock research; Stage A2; Stage B
- Limitations: All acquired artifact publication dates remain unknown in governed metadata.; Evidence is dominated by vendor-primary sources.; No PCB signal-integrity, material, process, test, yield or capacity evidence was acquired.

## 2. Evidence-grounded claims

### [GROUNDED] [claim: CLM-001 ]

Intel Gaudi documentation describes compute, memory and networking as three principal accelerator subsystems.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:a9fd768ade61b67b2689bbee / normalized_document:9f754e788c43c4614d38fb7a / section 23 / hash 5cc12224b817...

### [GROUNDED] [claim: CLM-002 ]

Intel Gaudi documentation states that integrated RoCE engines support inter-processor communication and can be used inside a server or rack and across racks.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: This establishes the vendor-described topology role, not comparative performance or an industry-wide route conclusion.
Evidence: evidence_artifact:a9fd768ade61b67b2689bbee / normalized_document:9f754e788c43c4614d38fb7a / section 38 / hash 9625c8d34faa...

### [GROUNDED] [claim: CLM-003 ]

Gaudi 3 is specified with 24 200-Gbps RDMA NIC ports.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:a9fd768ade61b67b2689bbee / normalized_document:9f754e788c43c4614d38fb7a / section 40 / hash 86b17e6ecee2...

### [GROUNDED] [claim: CLM-004 ]

DGX H100/H200 documentation lists eight GPUs, an NVSwitch/NVLink fabric and separate cluster and storage/management network interfaces.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:222da3eb56146c9604f09fca / normalized_document:aa0d4f097afc3db709bcfad1 / section 26 / hash 9dd1f5c62857...

### [GROUNDED] [claim: CLM-005 ]

DGX H100/H200 documentation specifies 900 GB/s GPU-to-GPU bandwidth for its fourth-generation NVLink configuration.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:222da3eb56146c9604f09fca / normalized_document:aa0d4f097afc3db709bcfad1 / section 43 / hash f768be3cedce...

### [GROUNDED] [claim: CLM-006 ]

DGX H100/H200 documentation specifies external cluster-network interfaces supporting up to 400 Gbps per listed card mode.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:222da3eb56146c9604f09fca / normalized_document:aa0d4f097afc3db709bcfad1 / section 55 / hash 7d54637b3383...

### [GROUNDED] [claim: CLM-007 ]

DGX B200 documentation lists eight GPUs, two fifth-generation NVLink switches and separate cluster and storage/management network interfaces.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:df8cb3fd0943596cdde66cd6 / normalized_document:8d9b94b1ce2f98ff9290a021 / section 26 / hash fd205c37eda8...

### [GROUNDED] [claim: CLM-008 ]

DGX B200 documentation specifies 14.4 TB/s aggregate bandwidth for two fifth-generation NVLink switches.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:df8cb3fd0943596cdde66cd6 / normalized_document:8d9b94b1ce2f98ff9290a021 / section 41 / hash 490bb4dc34f3...

### [GROUNDED] [claim: CLM-009 ]

DGX B200 documentation specifies external cluster-network interfaces supporting up to 400 Gbps per listed card mode.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:df8cb3fd0943596cdde66cd6 / normalized_document:8d9b94b1ce2f98ff9290a021 / section 53 / hash 564f200bca04...

### [GROUNDED] [claim: CLM-010 ]

The DGX SuperPOD reference architecture enumerates separate compute, storage and management network fabrics.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: The cited normalized section enumerates fabric categories but does not quantify all topology denominators.
Evidence: evidence_artifact:ab0129aeb5d659a68e30dd0d / normalized_document:1a99ba4dbda14777bea792a4 / section 52 / hash 0eaa0da4582b...

### [GROUNDED] [claim: CLM-011 ]

The BlueField-2 product brief describes a DPU combining network-adapter, programmable processing and infrastructure-offload functions.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: Vendor product positioning is not independent proof of workload benefit.
Evidence: evidence_artifact:b37fa65c89137b99055bf363 / normalized_document:6ab0c383b7a9cc3a5cd4bcd8 / section 0 / hash d585c95cac7a...

### [GROUNDED] [claim: CLM-012 ]

The BlueField-2 product brief specifies both network interfaces and a PCIe host interface.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: 
Evidence: evidence_artifact:b37fa65c89137b99055bf363 / normalized_document:6ab0c383b7a9cc3a5cd4bcd8 / section 3 / hash 2a8274ce5b7b...

### [GROUNDED] [claim: CLM-013 ]

Broadcom states that Tomahawk 5 provides 51.2 Tbps on one switch chip for data-center and AI/ML cluster applications.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: The short marketing page does not establish deployment scale, demand, bottleneck severity or source independence.
Evidence: evidence_artifact:3949f7abd9c7de6d9f1d7078 / normalized_document:c6c1370214775caa9b56711b / section 0 / hash 1e276ec9a4cd...

### [GROUNDED] [claim: CLM-014 ]

Lightmatter states that Passage supports 56–448 Gbps per lane and multiple wavelengths in a photonic interconnect platform.

- Type: fact
- Status: sufficient
- Confidence: medium
- Limitations: This is a vendor claim and does not establish adoption, comparative system economics or displacement.
Evidence: evidence_artifact:f4f5230306dfb92c8bb6b8e2 / normalized_document:42ff83d94ab9e8677c2d7887 / section 45 / hash 1e414b4619a1...

### [GROUNDED] [claim: CLM-015 ]

Cisco's C240 M7 general-purpose rack-server documentation emphasizes PCIe Gen5 expansion and network connectivity rather than an integrated accelerator scale-up fabric.

- Type: inference
- Status: sufficient
- Confidence: low
- Limitations: The comparison uses one general-purpose server product and cannot represent the entire traditional-server market.
Evidence: evidence_artifact:73c53b28d367b80db00542cc / normalized_document:c6d99a7cee7058815d558c12 / section 110 / hash ab54f88f0175...
Evidence: evidence_artifact:73c53b28d367b80db00542cc / normalized_document:c6d99a7cee7058815d558c12 / section 95 / hash dc1c3d666572...

### [GROUNDED] [claim: CLM-016 ]

Within the cited DGX system tables, internal GPU-to-GPU fabric and external cluster networking are distinct functional paths.

- Type: inference
- Status: sufficient
- Confidence: medium
- Limitations: This is a bounded architectural inference from one vendor family, not a universal topology law.
Evidence: evidence_artifact:222da3eb56146c9604f09fca / normalized_document:aa0d4f097afc3db709bcfad1 / section 55 / hash 7d54637b3383...
Evidence: evidence_artifact:222da3eb56146c9604f09fca / normalized_document:aa0d4f097afc3db709bcfad1 / section 26 / hash 9dd1f5c62857...
Evidence: evidence_artifact:222da3eb56146c9604f09fca / normalized_document:aa0d4f097afc3db709bcfad1 / section 43 / hash f768be3cedce...

## 3. Evidence-grounded technical mechanisms

### [GROUNDED] MECH-001: Integrated accelerator networking

Gaudi documentation explicitly organizes the accelerator around compute, memory and networking subsystems.

- The cited architecture treats networking as a principal accelerator subsystem. [claims: CLM-001]
- Tradeoffs: No comparative performance evidence
- Scope: Intel Gaudi architecture only.
- Confidence: medium

### [GROUNDED] MECH-002: RoCE-based scale-up and scale-out communication

Gaudi documentation directly links integrated RoCE engines to inside-server/rack and across-rack scaling.

- Integrated RoCE engines provide the documented inter-processor communication path. [claims: CLM-002]
- Port count and rate are explicit architecture parameters. [claims: CLM-003]
- Tradeoffs: No independent performance comparison
- Scope: Intel Gaudi generation described by the source.
- Confidence: medium

### [GROUNDED] MECH-003: NVLink and external network path separation

The DGX component table distinguishes NVLink/NVSwitch GPU communication from ConnectX external network interfaces.

- The system documentation lists an internal GPU communication fabric. [claims: CLM-004; CLM-005; CLM-007; CLM-008]
- The same systems list separate external cluster interfaces. [claims: CLM-006; CLM-009; CLM-016]
- Tradeoffs: No workload-level scaling data
- Scope: DGX H100/H200 and B200 documentation.
- Confidence: medium

### [GROUNDED] MECH-004: DPU network-host boundary

The BlueField product brief describes integrated network, processing and PCIe host interfaces.

- The DPU combines network-adapter and programmable processing roles. [claims: CLM-011]
- Network and PCIe interfaces define the host/network boundary. [claims: CLM-012]
- Tradeoffs: Benefit magnitude is not independently verified
- Scope: BlueField-2 product only.
- Confidence: medium

### [GROUNDED] MECH-005: Photonic interconnect boundary claim

Lightmatter publishes lane-rate and wavelength specifications for Passage; this grounds only the existence and stated specification of the route.

- The vendor specifies a photonic platform with explicit lane rates and wavelengths. [claims: CLM-014]
- Tradeoffs: Cost, power, packaging and manufacturability are unresolved
- Scope: Lightmatter Passage vendor claim only.
- Confidence: medium

## 4. Grounded causal analysis

### [GROUNDED] EDGE-001

NODE-ACCELERATOR → NODE-INTERNAL-FABRIC

- Mechanism: MECH-002
- Necessary conditions: The cited Gaudi topology is the applicable architecture.
- Alternatives: Other accelerators may use different internal fabrics.
- Failure conditions: The source architecture is not representative of the studied generation.

### [GROUNDED] EDGE-002

NODE-INTERNAL-FABRIC → NODE-EXTERNAL-FABRIC

- Mechanism: MECH-003
- Necessary conditions: Internal and external paths remain functionally distinct in the cited DGX system.
- Alternatives: Integrated networking architectures can blur the boundary.
- Failure conditions: A later architecture unifies the paths or uses a different topology.

### [GROUNDED] EDGE-003

NODE-DPU → NODE-EXTERNAL-FABRIC

- Mechanism: MECH-004
- Necessary conditions: The DPU is deployed at the host-network boundary described by the product brief.
- Alternatives: A conventional NIC and host CPU can perform the functions.
- Failure conditions: The product is not deployed in the target system.

## 5. Technology route comparisons

### ROUTE-001: Scale-up and scale-out

Gaudi documentation explicitly describes both scopes, but no independent comparison is available.

- Tradeoffs: Performance and cost comparisons are not available.
- Unresolved: Cross-vendor generality

### ROUTE-002: Ethernet and InfiniBand roles

Both appear in product and reference-architecture materials; no winner can be selected.

- Tradeoffs: No cost, latency or congestion-control evidence was acquired.
- Unresolved: Comparable workload benchmarks; deployment mix

### ROUTE-003: Electrical and photonic interconnect boundary

A photonic route exists as a vendor-stated alternative, but comparative judgment is not assessable.

- Tradeoffs: Power, cost, distance, packaging and manufacturability are unresolved.
- Unresolved: Independent validation; commercial maturity; system insertion point

## 6. Limited system bottleneck judgments

### [LIMITED JUDGMENT] BOT-001

Gaudi documentation calls the communication engines critical, but the current evidence does not quantify severity or unmet demand.

- Status: insufficient
- Counterarguments: High specified bandwidth does not prove a bottleneck.; No scaling benchmark or independent engineering evidence is available.
- Invalidation: Independent workload data show communication is not limiting in the relevant scope.

### [LIMITED JUDGMENT] BOT-002

Systems expose high-rate cluster interfaces and separate fabrics, but no evidence establishes present supply or performance shortage.

- Status: open
- Counterarguments: Interface capability is not evidence of binding constraint.; No utilization or congestion data is available.
- Invalidation: Measured fabric headroom remains ample across target workloads.

## 7. Unverified mechanism skeletons

### [SKELETON — NOT VERIFIED] SKEL-001

How do higher data rates change signal-integrity constraints?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: peer-reviewed signal-integrity research; relevant electrical-interconnect standards; engineering validation measurements
- Gap IDs: GAP-SIGNAL

### [SKELETON — NOT VERIFIED] SKEL-002

How do insertion-loss mechanisms change PCB material and geometry requirements?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: laminate loss-characterization data with test method; channel-loss simulations and measurements; standards defining the measurement method
- Gap IDs: GAP-LOSS

### [SKELETON — NOT VERIFIED] SKEL-003

What directly drives PCB layer-count changes in the relevant AI systems?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: board stack-up disclosures; system board schematics or engineering teardowns; independent PCB engineering analysis
- Gap IDs: GAP-LAYERS

### [SKELETON — NOT VERIFIED] SKEL-004

Which laminate and resin properties are required by the relevant channel budgets?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: laminate data sheets with Dk/Df test methods; channel-budget engineering documents; independent material qualification data
- Gap IDs: GAP-LAMINATE

### [SKELETON — NOT VERIFIED] SKEL-005

When and why are back-drilling processes required?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: via-stub and back-drill engineering studies; fabrication process windows; reliability and yield data
- Gap IDs: GAP-BACKDRILL

### [SKELETON — NOT VERIFIED] SKEL-006

How do lamination and layer alignment affect manufacturability?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: multilayer lamination process references; registration tolerance data; equipment and process capability studies
- Gap IDs: GAP-LAMINATION

### [SKELETON — NOT VERIFIED] SKEL-007

How do thermal and electrical constraints interact at board level?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: thermal-mechanical board studies; system thermal design documents; reliability standards
- Gap IDs: GAP-THERMAL

### [SKELETON — NOT VERIFIED] SKEL-008

What test methods and equipment are required for high-speed boards?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: high-speed PCB test standards; TDR/VNA and automated test specifications; production test coverage data
- Gap IDs: GAP-TEST

### [SKELETON — NOT VERIFIED] SKEL-009

Which process steps constrain qualified manufacturing yield?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: audited yield data; process defect Pareto data; independent manufacturing surveys
- Gap IDs: GAP-YIELD

### [SKELETON — NOT VERIFIED] SKEL-010

How should qualified effective capacity be distinguished from nominal PCB capacity?

- Candidate variables: system parameter; material or process parameter; measurement outcome
- Required evidence: qualified-product capacity disclosures; customer qualification timelines; utilization, mix and yield data
- Gap IDs: GAP-CAPACITY

## 8. Hypothesized causal edges and value questions

- [HYPOTHESIS] HEDGE-001: NODE-EXTERNAL-FABRIC → EXT-GAP-SIGNAL | gaps: GAP-SIGNAL; GAP-LOSS
- [HYPOTHESIS] HEDGE-002: EXT-GAP-SIGNAL → EXT-GAP-LAMINATE | gaps: GAP-SIGNAL; GAP-LOSS; GAP-LAMINATE
- [HYPOTHESIS] HEDGE-003: EXT-GAP-LAYERS → EXT-GAP-YIELD | gaps: GAP-LAYERS; GAP-LAMINATION; GAP-YIELD
- [VALUE QUESTION] VAL-001: Whether higher interconnect requirements increase PCB technical content remains an open industry-segment question. | status: evidence_gap_linked
- [VALUE QUESTION] VAL-002: Whether photonic interconnect changes the boundary of electrical board-level links is not eligible for judgment. | status: not_eligible_for_judgment
- [VALUE QUESTION] VAL-003: Whether manufacturing complexity changes qualified effective capacity remains open. | status: evidence_gap_linked

## 9. Evidence gaps

### [EVIDENCE GAP] GAP-BACKDRILL

When and why are back-drilling processes required?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: via-stub and back-drill engineering studies; fabrication process windows; reliability and yield data

### [EVIDENCE GAP] GAP-CAPACITY

How should qualified effective capacity be distinguished from nominal PCB capacity?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: qualified-product capacity disclosures; customer qualification timelines; utilization, mix and yield data

### [EVIDENCE GAP] GAP-LAMINATE

Which laminate and resin properties are required by the relevant channel budgets?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: laminate data sheets with Dk/Df test methods; channel-budget engineering documents; independent material qualification data

### [EVIDENCE GAP] GAP-LAMINATION

How do lamination and layer alignment affect manufacturability?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: multilayer lamination process references; registration tolerance data; equipment and process capability studies

### [EVIDENCE GAP] GAP-LAYERS

What directly drives PCB layer-count changes in the relevant AI systems?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: board stack-up disclosures; system board schematics or engineering teardowns; independent PCB engineering analysis

### [EVIDENCE GAP] GAP-LOSS

How do insertion-loss mechanisms change PCB material and geometry requirements?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: laminate loss-characterization data with test method; channel-loss simulations and measurements; standards defining the measurement method

### [EVIDENCE GAP] GAP-SIGNAL

How do higher data rates change signal-integrity constraints?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: peer-reviewed signal-integrity research; relevant electrical-interconnect standards; engineering validation measurements

### [EVIDENCE GAP] GAP-TEST

What test methods and equipment are required for high-speed boards?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: high-speed PCB test standards; TDR/VNA and automated test specifications; production test coverage data

### [EVIDENCE GAP] GAP-THERMAL

How do thermal and electrical constraints interact at board level?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: thermal-mechanical board studies; system thermal design documents; reliability standards

### [EVIDENCE GAP] GAP-YIELD

Which process steps constrain qualified manufacturing yield?

- Why insufficient: The current Stage A evidence consists primarily of system and vendor product materials and does not contain the required PCB engineering or manufacturing evidence.
- Required evidence: audited yield data; process defect Pareto data; independent manufacturing surveys

## 10. Contradictions and uncertainty

- [UNCERTAINTY] UNC-001: ER05 mixes server, rack, accelerator and port denominators that cannot be reconciled.
- [UNCERTAINTY] UNC-002: Governed acquisition metadata retains unknown publication dates for all acquired artifacts.
- [UNCERTAINTY] UNC-003: Most evidence is vendor-primary and independent professional secondary evidence is missing.
- [UNCERTAINTY] UNC-004: Lightmatter Passage specifications are vendor claims and do not establish adoption or displacement.
- [UNCERTAINTY] UNC-005: DGX H100 and SuperPOD content was acquired in multiple ER contexts but counts as one content chain per original document.
- [UNCERTAINTY] UNC-006: The Supermicro GPU-system candidate remained blocked and contributes no acquired evidence coverage.

## 11. Verification and falsification

- VER-001: Accelerator scaling efficiency and communication share; invalidation: Communication share remains non-binding.
- VER-002: Internal versus external fabric utilization; invalidation: Architecture unifies or bypasses the paths.
- VER-003: Energy per bit, reach and packaging yield; invalidation: No comparable validated data exists.
- VER-004: Measured channel loss and eye-margin data; invalidation: Results are not reproducible or scope mismatched.
- VER-005: Qualified yield and product-mix-adjusted capacity; invalidation: Only nominal capacity or promotional claims are available.

## 12. Current bounded conclusion

The current evidence supports partial demand-side cognition of AI accelerator and network-interconnect architecture. It does not support complete AI PCB material, manufacturing, bottleneck or value-migration cognition.
