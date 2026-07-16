# Wave D Five-Theme Deep Research Design

**Date:** 2026-07-16

## Goal

Add five high-value deep-research themes after Waves A-C while keeping the Industry Catalog as the structural directory and Theme Research as the readable investment-research layer.

Wave D must answer, for every theme:

- What is the value chain and where does value accrue?
- Which public companies have a direct, evidenced relationship?
- Is the relevant revenue material, broad, undisclosed, or still pre-commercial?
- Which catalog nodes belong to the research theme, including one research stage mapping to multiple canonical L3/L4 nodes?
- What should the reader monitor next to validate or falsify the thesis?

## Selected Themes

| Order | Chain ID | Proposed theme ID | Why it belongs in Wave D |
| --- | --- | --- | --- |
| D1 | `semiconductor_eda_ip_design_services` | `semiconductor_eda_ip_design_services_value_chain_v1` | Completes the upstream semiconductor bottleneck from EDA and IP through design services; complements compute chips, equipment, materials and packaging without duplicating them. |
| D2 | `memory_chips_storage_control` | `memory_chips_storage_control_value_chain_v1` | Adds the memory-bandwidth and storage-control constraint that is missing from the current AI compute and data-center research set. |
| D3 | `industrial_machine_tools_cnc` | `industrial_machine_tools_cnc_value_chain_v1` | Covers the manufacturing-equipment base layer behind automation, robots and core mechanical components, with clear domestic-substitution and order-to-revenue boundaries. |
| D4 | `satellite_manufacturing_space_infrastructure` | `satellite_manufacturing_space_infrastructure_value_chain_v1` | Extends commercial-space research from launch into satellite platform, payload, ground infrastructure and in-orbit deployment, where company beneficiaries differ materially from launch providers. |
| D5 | `high_end_medical_devices` | `high_end_medical_devices_value_chain_v1` | Adds a non-cyclical technology vertical with readable product, registration, installed-base and service-revenue evidence, improving sector diversity. |

## Research Boundary

### D1 — Semiconductor EDA, IP, and Design Services

Research stages should consolidate readable investment logic rather than mirror every catalog leaf:

1. EDA tool chain and process-design kits
2. Semiconductor IP licensing and royalty model
3. IC design services, verification and tape-out enablement
4. Advanced-process and domestic-ecosystem qualification
5. Commercialization, customer concentration and recurring revenue

Do not attribute foundry, chip-product or generic software revenue to this theme. EDA/IP revenue must be separately disclosed or marked `undisclosed`.

### D2 — Memory Chips, Storage, and Controllers

1. DRAM, NAND and specialty-memory architecture
2. Memory-interface and controller chips
3. Enterprise SSD and storage systems
4. Packaging, testing and module integration dependencies
5. Capacity, pricing cycle, customer qualification and inventory risk

Do not treat storage-module revenue as memory-wafer revenue. AI-memory claims require explicit product or customer evidence; HBM concept association alone is insufficient.

### D3 — Industrial Machine Tools and CNC

1. CNC systems, servo drives and feedback control
2. Machine-tool bodies, spindles and functional components
3. High-end cutting, grinding and multi-axis processing
4. Aerospace, automotive and precision-manufacturing validation
5. Orders, acceptance, installed base, service and replacement cycle

Orders, contract value and delivery quantity do not equal recognized revenue. Generic industrial automation ownership remains on its canonical chain.

### D4 — Satellite Manufacturing and Space Infrastructure

1. Satellite platform and structural systems
2. Payload, onboard electronics and power systems
3. Ground measurement, control and gateway infrastructure
4. Batch manufacturing, launch integration and in-orbit delivery
5. Constellation deployment, utilization and service validation

Launch-vehicle ownership remains in `commercial_space_launch`. Announced constellation capacity, successful launch and satellite delivery do not establish recurring service revenue.

### D5 — High-End Medical Devices

1. Core device platform and high-value consumables
2. Key components, detectors, control systems and software
3. Clinical registration, hospital access and localization
4. Installed base, procedure volume and service revenue
5. Reimbursement, procurement, compliance and collection risk

Registration acceptance, hospital trials and tender wins do not equal stable revenue. Medical imaging nodes remain on their canonical chain when ownership is more specific there.

## Data Contract

Each theme ships four coordinated artifacts:

1. Theme artifact with readable nodes, claims and seven research sections.
2. Company-mapping artifact with reviewed beneficiary tiers.
3. Accepted source pack.
4. Node-evidence matrix.

Every package must satisfy:

- at least 10 accepted sources;
- at least 8 primary official filings or regulator/official sources;
- at least 12 reviewed claims;
- at least 8 reviewed company mappings;
- exactly seven readable research sections;
- no unused source, claim, evidence item or company mapping;
- explicit evidence gaps instead of silent omission.

## Evidence Contract

The Wave B cloud review findings become mandatory Wave D rules:

1. For every source attached to a claim, all `affected_theme_nodes` of that claim must be a subset of the source pack's `supported_node_ids`.
2. Source pack, claim graph and node matrix must be bidirectionally exact.
3. Broad value-flow, catalyst or risk claims cannot implicitly attach every source to every node.
4. Every reviewed company mapping must contain three distinct evidence items:
   - product or service relationship;
   - revenue/materiality boundary;
   - business stage or risk.
5. Each evidence item must have a precise page locator. Phrases such as “风险章节” or “收入分析页” without page numbers are invalid.
6. Product capability, customer qualification, order value, project construction and stable recognized revenue must remain separate states.

## Catalog Linking

Use the approved one-to-many pair model:

- one research node may map to multiple canonical L3/L4 catalog nodes;
- the exact `(theme_node_id, catalog_node_id)` pair must be unique;
- one catalog node may have only one owning research node inside a theme link;
- cross-chain dependencies remain unmapped and are named explicitly in the theme narrative;
- projection must preserve every pair without collapsing repeated research-node IDs.

Catalog links are added only after the theme node design is frozen. Empty placeholder links are not considered completion.

## Company Read Model

Company mappings keep the established beneficiary tiers:

- `core_beneficiary`: relevant business is a material, disclosed operating segment;
- `elastic_beneficiary`: direct product/service relationship exists but narrow revenue is undisclosed or not yet material;
- `indirect_beneficiary`: dependency or adjacent supplier with canonical ownership elsewhere;
- `concept_association`: insufficient for the reviewed company table and normally excluded.

The company table has no action column. A row click opens the Stock Workspace and preserves `source=theme_research`.

## Delivery Order

Wave D executes sequentially by evidence complexity:

1. D1 EDA/IP/design services
2. D2 memory/storage/controllers
3. D3 industrial machine tools/CNC
4. D4 satellite manufacturing/space infrastructure
5. D5 high-end medical devices

Each theme receives a focused spec review and data-quality review before the next theme begins. Wave readiness is reported only after all five themes and the full prior 20-theme pool remain ready.

## Acceptance

Wave D is complete when:

- Wave D reports `5/5 ready`;
- the combined pool reports `25/25 ready`;
- every theme renders list, detail, nodes, sources, claims and companies routes;
- catalog projections preserve all one-to-many pairs;
- company row clicks open the correct Stock Workspace;
- all source/claim/node/matrix reverse audits pass;
- all company evidence locators are precise and role-specific;
- Waves A-C and the original five themes remain unchanged and ready.

