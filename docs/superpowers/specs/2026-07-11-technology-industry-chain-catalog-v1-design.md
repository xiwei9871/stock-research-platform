# Technology Industry Chain Catalog v1 Design

Updated: 2026-07-11

## 1. Purpose

Build a complete technology-industry catalog before expanding evidence packs and company mappings theme by theme.

The catalog is the structural backbone for the existing Theme-driven Research Engine and Tech Bottleneck workflow. It is not derived from the current stock universe and does not treat listed-company coverage as the boundary of technology research.

The current production Tech Bottleneck review universe contains 461 companies:

- 378 companies in the original frontend dataset;
- 83 companies added through omission-rescue review;
- 461 is the current coverage-audit baseline, not a permanent taxonomy count.

The catalog must answer:

```text
Which technology industries exist?
  -> What independent industry chains do they contain?
  -> What systems, processes, and technical routes make up each chain?
  -> Which atomic equipment, material, component, software, or service nodes matter?
  -> Where are value capture, bottlenecks, localization gaps, and supply constraints?
  -> Which companies map to each node, and with what evidence?
```

## 2. External Research Baseline

The catalog uses public policy and industry sources as boundary references, while reorganizing them for research use.

Primary policy references:

- MIIT and other ministries, *New Industry Standardization Pilot Project Implementation Plan (2023-2035)*: eight emerging-industry areas and nine future-industry areas.
  - https://www.gov.cn/zhengce/zhengceku/202308/content_6899527.htm
- MIIT and other ministries, *Implementation Opinions on Promoting Future Industry Innovation and Development*: future manufacturing, information, materials, energy, space, and health.
  - https://www.gov.cn/zhengce/zhengceku/202401/content_6929021.htm
- MIIT, *Guiding Opinions on the Innovative Development of Humanoid Robots*: brain, cerebellum, limbs, machine body, perception, control, and high-precision sensing.
  - https://www.miit.gov.cn/jgsj/kjs/wjfb/art/2023/art_50316f76a9b1454b898c7bb2a5846b79.html

Industry process references used by the first pilots:

- ASML chip-manufacturing process overview:
  - https://www.asml.com/en/technology/all-about-microchips/how-microchips-are-made
- Lam Research semiconductor process-equipment categories:
  - https://www.lamresearch.com/products/
- NVIDIA 800 VDC data-center power architecture:
  - https://www.nvidia.cn/data-center/technologies/800-vdc-architecture/
- IEA, *Energy and AI*:
  - https://www.iea.org/reports/energy-and-ai

Policy taxonomies are authoritative scope references but are too broad to serve directly as research trees. The platform therefore preserves policy traceability while using investment-research-oriented chain boundaries.

## 3. Catalog Hierarchy

```text
L1 technology sector
└── L2 independently researchable industry chain
    └── L3 subsystem, manufacturing stage, or technical route
        └── L4 atomic research node
```

### L1

An enduring technology sector used for top-level navigation and coverage reporting.

### L2

An industry chain capable of supporting an independent answer to:

- chain structure;
- value capture;
- bottleneck and localization status;
- company mapping;
- evidence gaps.

### L3

One of:

- manufacturing-process stage;
- system or functional subsystem;
- infrastructure-flow stage;
- technical route.

### L4

The smallest canonical research node. It must represent identifiable equipment, material, component, software, or service and support independent scoring, evidence, and company mapping.

Companies, technical routes, evidence, and assessments attach to L4 nodes. They are not extra fixed tree levels.

## 4. L1 Master Catalog

1. Semiconductor and electronic core industries
2. Next-generation information technology
3. High-end equipment and intelligent manufacturing
4. Energy technology and new power systems
5. Advanced materials
6. Intelligent vehicles and advanced transportation
7. Aerospace, low-altitude, and ocean technology
8. Life sciences and medical technology
9. Green low-carbon and resource recycling
10. Frontier and future technology

Semiconductors remain an independent L1 because their design, manufacturing, equipment, material, packaging, and component structures are too large and bottleneck-intensive to hide under information technology.

## 5. L2 Master Catalog

### 5.1 Semiconductor and electronic core industries

- EDA, semiconductor IP, and design services
- AI, CPU, GPU, FPGA, and logic chips
- memory chips and storage control
- analog, mixed-signal, and RF chips
- power semiconductors
- MEMS and intelligent sensors
- wafer manufacturing and specialty processes
- semiconductor manufacturing equipment
- semiconductor materials and electronic chemicals
- packaging, test, and advanced packaging
- PCB, passive components, connectors, and electronic interconnect
- display panels and optoelectronic components

### 5.2 Next-generation information technology

- AI foundation models and application software
- AI compute infrastructure
- cloud and data-center infrastructure
- 5G, 6G, and mobile communications
- optical communications and data-center interconnect
- network equipment, edge computing, and IoT
- foundational software, operating systems, and databases
- industrial software
- cybersecurity, data security, and data infrastructure

### 5.3 High-end equipment and intelligent manufacturing

- industrial machine tools and CNC systems
- industrial automation, PLC, DCS, and servo control
- industrial robots
- humanoid robots and embodied intelligence
- laser equipment and additive manufacturing
- scientific instruments
- industrial inspection, metrology, and machine vision
- bearings, screws, hydraulics, seals, and core mechanical components
- process-industry and specialized production equipment

### 5.4 Energy technology and new power systems

- new power systems and smart grids
- power-generation and energy equipment
- AI data-center power
- solar power
- wind power
- power batteries and battery materials
- new energy storage
- hydrogen and fuel cells
- nuclear power and nuclear-energy equipment

### 5.5 Advanced materials

- high-temperature alloys, specialty steel, and advanced metals
- rare earths, permanent magnets, and critical mineral materials
- carbon fiber and advanced composites
- advanced ceramics, specialty glass, and inorganic materials
- high-performance polymers and engineering plastics
- membrane and separation materials
- nanomaterials and other functional materials

### 5.6 Intelligent vehicles and advanced transportation

- new-energy vehicle architecture and platforms
- intelligent driving and smart cockpits
- automotive electronics and automotive-chip applications
- electric drive, chassis-by-wire, and thermal management
- rail-transit equipment
- intelligent transportation and vehicle-road-cloud infrastructure

### 5.7 Aerospace, low-altitude, and ocean technology

- civil aircraft and aero engines
- commercial space launch
- satellite manufacturing and space infrastructure
- satellite communications, navigation, remote sensing, and applications
- UAV, eVTOL, and low-altitude economy
- ships, offshore engineering, and deep-sea equipment
- defense electronics and special equipment

### 5.8 Life sciences and medical technology

- small-molecule innovative drugs
- biologic and antibody drugs
- vaccines
- cell and gene therapy
- synthetic biology and biomanufacturing
- high-end medical devices
- medical imaging and diagnostic equipment
- in-vitro diagnostics
- digital health and healthcare IT
- agricultural biotechnology and modern seed industries

### 5.9 Green low-carbon and resource recycling

- air, soil, and industrial pollution control
- water treatment and water-resource technology
- solid waste, resource recovery, and circular economy
- carbon capture, utilization, and storage
- industrial energy conservation and efficiency management

### 5.10 Frontier and future technology

- quantum computing, communication, and measurement
- brain-computer interfaces and neural engineering
- controlled nuclear fusion
- future networks and next-generation internet
- spatial computing, XR, and metaverse infrastructure
- future displays
- photonic, in-memory, neuromorphic, and other new computing routes

The L2 catalog is versioned. Additions require evidence that a proposed chain is independently researchable rather than merely a market label or one component.

## 6. Chain Kinds

Every L2 chain must declare one kind:

```text
canonical_industry_chain
application_theme_chain
frontier_technology_chain
```

### Canonical industry chain

Owns canonical L4 nodes and company mappings. Examples:

- semiconductor manufacturing equipment;
- humanoid robots and embodied intelligence;
- industrial machine tools.

### Application theme chain

Composes canonical nodes from multiple industries without duplicating them. Examples:

- AI data-center power;
- intelligent vehicle-road-cloud systems;
- satellite internet.

An application role uses `canonical_node_refs`. Formal company mappings remain on canonical nodes and are aggregated into the theme view.

### Frontier technology chain

Organizes competing technical routes before product and supply-chain boundaries stabilize. Examples:

- quantum computing;
- controlled fusion;
- brain-computer interfaces.

These chains emphasize route maturity, experimental milestones, enabling equipment, and commercialization gates.

## 7. Decomposition Templates

Four templates share the same L1-L4 hierarchy:

### Manufacturing process

```text
design -> materials -> manufacturing -> process control -> packaging/delivery
```

Used by semiconductors, batteries, solar power, and innovative drugs.

### System architecture

```text
perception -> compute/control -> execution -> energy -> structure -> software
```

Used by robots, vehicles, aircraft, and medical equipment.

### Infrastructure flow

```text
resource/input -> access -> conversion -> transmission/distribution
-> endpoint delivery -> operation
```

Used by power, AI compute, communications, and data centers.

### Technical route

```text
route -> core components -> enabling conditions -> performance bottleneck
-> scale-up gate -> commercial application
```

Used by quantum, storage, hydrogen, and frontier materials.

## 8. Unique Ownership and Graph Relationships

Every canonical L4 node has one `primary_path`.

Cross-industry relationships use typed edges rather than duplicate nodes:

```text
depends_on
enables
supplies
uses
substitutes
competes_with
downstream_of
canonical_node_refs
```

Examples:

- power-battery cells belong to the battery chain; NEV architecture references them;
- automotive chips belong to semiconductor chains; vehicle chains describe qualification and system use;
- semiconductor materials belong to semiconductor chains; advanced materials provide cross-sector material context;
- satellite space segments belong to aerospace; terrestrial optical and network equipment remains in information technology;
- humanoid joints `use` motors, reducers, encoders, and bearings instead of duplicating those components by body location;
- AI data-center power references grid, transformer, semiconductor, copper, power-supply, and cooling nodes.

## 9. L4 Research Contract

Every canonical L4 node supports:

```text
node_id
node_name
primary_path
node_type
description
technology_maturity
value_capture_score
bottleneck_score
localization_gap_score
supply_tightness_score
evidence_strength
key_metrics
technical_routes
overseas_leaders
domestic_players
company_mappings
source_ids
claim_ids
review_status
```

Scores remain 0-5 and follow the existing Theme Research evidence gates. A high score without adequate evidence is an evidence-gap priority, not a reviewed conclusion.

## 10. Pilot Trees

### Semiconductor manufacturing equipment

Ten L3 process families:

- lithography and patterning;
- etch;
- thin-film deposition and epitaxy;
- thermal processing and doping;
- clean and wet processing;
- CMP and surface planarization;
- inspection, metrology, and process control;
- wafer handling and fab automation;
- vacuum, gas, and fluid control;
- facilities and pollution control.

The pilot contains roughly 60 L4 nodes and validates manufacturing-process decomposition.

### Humanoid robots and embodied intelligence

Twelve L3 system families:

- embodied-intelligence brain;
- motion-control cerebellum;
- data, training, and simulation;
- perception;
- compute and control hardware;
- rotary actuators;
- linear actuators;
- upper limbs and dexterous hands;
- lower limbs and locomotion;
- body structure and lightweighting;
- energy and thermal management;
- manufacturing, test, and integration.

The pilot validates system-architecture decomposition. The existing humanoid artifact remains draft until the Phase 2B evidence pack is complete.

### AI data-center power

Eleven L3 infrastructure roles:

- AI load and capacity planning;
- energy supply and resilience;
- grid access and substations;
- backup power;
- UPS and medium/low-voltage conversion;
- HVDC and new DC architectures;
- room and rack distribution;
- server and board-level power;
- liquid cooling and thermal management;
- energy-management software;
- design, EPC, commissioning, and operations.

This pilot validates application-theme composition and canonical references.

## 11. Catalog Data Objects

The first implementation remains artifact-first and read-only.

Proposed objects:

```text
technology_sector       # L1
industry_chain          # L2 and chain_kind
industry_node           # L3/L4
industry_edge           # typed cross-chain relationship
theme_composition       # application role -> canonical nodes
catalog_source          # taxonomy and process source
coverage_snapshot       # current universe coverage at a point in time
```

The catalog does not initially write company mappings or scores into production tables. It reuses the existing Theme Research schema and review gates through adapters after the hierarchy is stable.

## 12. Delivery Waves

These waves are separate from the completed Theme Research phases 0-10.

### Catalog Wave 0: Design freeze

- freeze L1 catalog, initial L2 catalog, chain kinds, hierarchy semantics, and ownership rules;
- record external source references;
- approve the three pilot decompositions.

### Catalog Wave 1: Read-only catalog foundation

- define versioned JSON schema and artifacts;
- implement offline loader and deterministic validation;
- validate IDs, parent references, chain kinds, primary ownership, and graph edges;
- provide CLI summary and coverage reporting;
- do not write the database.

### Catalog Wave 2: Three pilot artifacts

- semiconductor manufacturing equipment;
- humanoid robots and embodied intelligence;
- AI data-center power;
- migrate existing AI power and humanoid theme structures through explicit adapters;
- preserve current review states and evidence semantics.

### Catalog Wave 3: Complete L2 skeleton

- register every approved L2 chain;
- assign chain kind and decomposition template;
- add scope, exclusions, aliases, and cross-chain ownership notes;
- allow incomplete L3/L4 branches to remain explicitly `skeleton`.

### Catalog Wave 4: Canonical-tree expansion

Expand L3/L4 in research-priority batches:

1. semiconductor, AI compute, communications, industrial software;
2. high-end equipment, robotics, power systems, energy storage;
3. advanced materials, intelligent vehicles, aerospace and low-altitude;
4. life sciences, green technology, and frontier technology.

No branch becomes reviewed merely because its tree is structurally complete.

### Catalog Wave 5: Current-universe coverage audit

- overlay the current 461-company review universe;
- report covered, unmapped, multi-mapped, and suspiciously broad mappings;
- identify catalog nodes with no A-share representation separately from data gaps;
- store the universe count and generation in a dated snapshot rather than hard-coding 461.

### Catalog Wave 6: Evidence and company mapping

- reuse source, claim, node, and mapping review gates;
- map companies only at canonical L4 nodes;
- distinguish direct product, component supplier, equipment supplier, material supplier, integrator, and downstream customer;
- require business materiality and evidence;
- complete the humanoid Phase 2B source pack before reviewed promotion.

### Catalog Wave 7: Production integration

- add read-only catalog APIs and dashboard tree navigation;
- show tree completeness, company coverage, reviewed evidence, and evidence gaps separately;
- integrate catalog context into Tech Bottleneck and Theme Research without replacing existing review records;
- consider database migration only after artifact schemas and pilots are stable.

## 13. Acceptance Criteria

- all ten L1 sectors and approved L2 chains are present;
- every L2 declares a chain kind and decomposition template;
- every canonical L4 node has one primary path;
- duplicate canonical ownership is rejected;
- all parent and cross-chain references resolve;
- application themes aggregate canonical nodes without copying company mappings;
- the 461-company universe is treated as a dated coverage snapshot;
- structural completeness, evidence completeness, and company coverage are reported separately;
- current Theme Research and Tech Bottleneck production semantics remain unchanged;
- short-video and oral claims remain research leads rather than accepted evidence.

## 14. Explicit Non-goals for v1

- automatic stock recommendation or ranking for trading;
- automatic promotion of catalog nodes to reviewed;
- exhaustive company mapping during catalog construction;
- replacing the current Tech Bottleneck review universe;
- treating policy labels as sufficient industry evidence;
- building a complex graph visualization before the catalog and evidence model are stable.
