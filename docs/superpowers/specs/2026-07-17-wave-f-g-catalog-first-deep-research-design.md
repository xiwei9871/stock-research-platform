# Wave F/G Catalog-First Deep Research Design

Date: 2026-07-17
Status: approved

## Goal

Select and prepare ten additional deep-research industry chains as Wave F and Wave G while preserving the Technology Industry Catalog as the permanent structural foundation of the research platform.

The catalog is the tree trunk. Theme Research is the evidence-backed reading and analysis layer grown from that tree. Market attention may determine delivery order, but it must never create, rename, merge, or redefine an industry chain.

## Approved Decisions

1. Every Wave F/G theme must use an exact existing L2 `chain_id` from the approved 82-chain catalog.
2. The catalog owns the canonical L1-L4 taxonomy, ownership path, scope, exclusions, and cross-chain relationships.
3. An unexpanded L2 skeleton must receive a valid L3/L4 decomposition before its Theme Research package is considered structurally ready.
4. Theme Research adds conclusions, claims, sources, evidence gaps, company mappings, beneficiary tiers, and update history without redefining the catalog tree.
5. Company mappings attach to specific investment-relevant L4 research objects. L2-only keyword association is insufficient.
6. Market-mainline strength ranks compliant chains; it does not determine their structure.
7. `synthetic_biology_biomanufacturing` is not selected for Wave G. It remains a valid catalog chain for a later wave.
8. Wave G position five is `scientific_instruments`.

## Canonical Hierarchy

The required relationship is:

```text
L1 sector
  -> L2 approved industry chain
    -> L3 segment, system, manufacturing stage, infrastructure stage, or route
      -> L4 canonical research object
        -> Theme Research node assessment, claims, sources, and evidence gaps
          -> evidence-backed company mapping and beneficiary tier
```

The market-mainline overlay operates only after this hierarchy exists:

```text
catalog ownership and boundaries
  -> structural decomposition
    -> evidence and company coverage
      -> market-priority ordering
```

This prevents a market label from becoming an unsupported parallel taxonomy.

## Selected Chains

### Wave F: strongest current mainlines

| Order | Catalog chain | Deep-research focus | Required boundary |
| --- | --- | --- | --- |
| F1 | `ai_foundation_models_application_software` | Foundation models, agents, application software, delivery models, adoption, and monetization | Compute chips, servers, data centers, and power infrastructure remain with their existing canonical chains |
| F2 | `uav_evtol_low_altitude_economy` | UAV and eVTOL platforms, flight control, avionics, propulsion, airframe, operations, and low-altitude infrastructure | Commercial launch and satellite infrastructure remain with aerospace and satellite chains |
| F3 | `mobile_communications_5g_6g` | 5G-A and 6G radio access, core network, RF systems, testing, network deployment, and commercialization gates | Satellite communication remains with `satellite_communications_navigation_remote_sensing`; generic edge/IoT equipment remains with its canonical chain |
| F4 | `analog_mixed_signal_rf_chips` | Analog, mixed-signal, RF, interface, data-conversion, and signal-chain chips | AI logic chips, memory, power semiconductors, packaging, and equipment remain with their existing chains |
| F5 | `rare_earth_permanent_magnets_critical_minerals` | Resource extraction, separation, metals and alloys, permanent magnets, recycling, supply security, and price transmission | Generic advanced metals and downstream equipment remain with their canonical chains |

### Wave G: next five durable mainlines

| Order | Catalog chain | Deep-research focus | Required boundary |
| --- | --- | --- | --- |
| G1 | `mems_intelligent_sensors` | MEMS design, fabrication, packaging, calibration, sensor fusion, and intelligent-sensor products | Application industries provide demand evidence but do not take ownership of the sensor nodes |
| G2 | `wafer_manufacturing_specialty_processes` | Foundry platforms, mature and specialty processes, process qualification, utilization, yield, and customer mix | Equipment, electronic materials, packaging, and downstream chip design remain with their canonical chains |
| G3 | `civil_aircraft_aero_engines` | Civil aircraft, aero engines, airborne systems, key components, certification, production ramp, and MRO | Low-altitude aircraft, commercial space, and defense-special equipment remain with their canonical chains |
| G4 | `nuclear_power_equipment` | Nuclear-island and conventional-island equipment, instrumentation and control, valves, fuel services, construction, commissioning, and maintenance | Controlled nuclear fusion remains with `controlled_nuclear_fusion` |
| G5 | `scientific_instruments` | Analytical, laboratory, spectroscopy, chromatography, microscopy, precision measurement, and research instruments | Production-line machine vision and metrology remain with `industrial_inspection_metrology_machine_vision`; medical imaging remains with its medical chain |

All ten records are existing `canonical_industry_chain` L2 entries. At the 2026-07-17 design audit, they are registered as `skeleton` chains and do not yet have complete chain-specific L3/L4 node artifacts. Selection therefore authorizes structural expansion and deep research; it does not imply that the branches are already research-ready.

## Why Scientific Instruments Replaces Synthetic Biology

`synthetic_biology_biomanufacturing` is a valid catalog L2 chain, but its near-term A-share mappings frequently depend on platform narratives, pilot capacity, or unquantified future products. That increases the risk of concept-only beneficiary lists in a wave intended to produce immediately readable company research.

`scientific_instruments` is preferred for Wave G because:

- its catalog ownership is independent and stable;
- the system architecture can be decomposed into identifiable products and subsystems;
- product registration, tender, customer adoption, installed base, service, and revenue evidence are usually observable;
- localization, qualification, precision, software, consumables, and service create explicit value-capture questions;
- company mappings can terminate at concrete L4 instruments and components rather than a general market label;
- it has less overlap with the already selected AI compute, AI power, optical communication, power semiconductor, and medical-device themes.

Synthetic biology remains in the 82-chain catalog and may be selected later when its L3/L4 structure and primary company evidence can support the same review gates.

## Catalog-First Delivery Contract

Each selected chain must pass the following stages in order.

### Stage 1: freeze the L2 contract

Use the existing catalog record unchanged unless an actual catalog defect is separately reviewed. Preserve:

- exact `chain_id`, sector, chain kind, and decomposition method;
- description, scope, exclusions, aliases, status, and order;
- canonical ownership of related objects in other chains.

Wave work must not silently edit the L2 boundary to fit available company evidence.

### Stage 2: expand canonical L3/L4 structure

Create a chain-specific catalog node artifact that follows the declared decomposition method.

Every L3 node must represent a durable organizing stage. Every L4 node must be a concrete research object that can own evidence and company mappings. Canonical L4 nodes require stable canonical keys and one ownership path.

Before Theme Research content is accepted:

- parent and primary paths must validate;
- L4 ownership must be unique;
- cross-chain dependencies must use typed edges or canonical references;
- application demand must not duplicate the supplied component;
- empty, decorative, or market-slogan nodes are prohibited;
- exclusions from the L2 record must be reflected in the node design.

### Stage 3: link catalog nodes to Theme Research

Create one Theme Research record for the L2 chain and explicit links between canonical catalog nodes and Theme Research assessment nodes.

The default theme ID is:

```text
<chain_id>_value_chain_v1
```

Any exception requires an explicit compatibility reason. FastAPI and React must consume shared registry or artifact-discovery paths; theme-specific routing branches are not allowed.

### Stage 4: build readable research content

Every theme must answer:

1. What does the chain produce or enable?
2. How does value, material, data, energy, or service flow through L3 stages?
3. Which L4 objects are bottlenecks or profit pools, and why?
4. What are the observable demand, policy, technology, capacity, and pricing catalysts?
5. What evidence would invalidate the thesis?
6. Which listed companies supply each relevant L4 object?
7. Is each company a core, elastic, indirect, or concept-only beneficiary?
8. Which claims, mappings, materiality estimates, or nodes remain unproven?

The research page must expose the directory-derived value chain, not a second independently invented structure.

### Stage 5: map companies through L4 evidence

Every reviewed company mapping must include:

- company code and name;
- catalog L4 node and linked Theme Research node;
- product or service relationship;
- mapping type and business stage;
- business materiality and disclosed revenue relevance;
- benefit-transmission explanation;
- bottleneck relevance and confidence;
- accepted supporting sources and publication dates;
- review status and unresolved gaps.

The default beneficiary table shows only reviewed core, elastic, and indirect beneficiaries. Concept associations remain in a separate evidence-gap section.

Company rows must continue to open Stock Workspace by clicking the row. No separate `操作` column is introduced.

### Stage 6: expose one consistent product surface

The Industry Catalog remains the directory:

- it shows the L1-L4 structure and deep-research status;
- it does not copy full claims, source packs, or company tables;
- `进入深度研究` opens the linked Theme Research record.

Theme Research remains the reading surface:

- it renders the directory-derived value-chain map;
- it owns conclusions, assessments, claims, evidence, company mappings, and update history;
- it links company rows to Stock Workspace;
- it clearly shows incomplete or unreviewed states.

## Research And Review Gates

A Wave F/G chain cannot be marked `已审核` until:

- the L2 record resolves to exactly one approved catalog chain;
- all required L3/L4 nodes validate under the catalog schema;
- every investment-relevant L4 object has an assessment or explicit evidence-gap state;
- the Theme Research value-chain order is derived from the catalog structure;
- at least ten accepted sources exist, including at least four primary or first-party sources;
- at least ten structured claims cover value capture, barriers, catalysts, and risks;
- every reviewed claim references accepted evidence;
- at least eight reviewed A-share company mappings exist when the chain genuinely supports that breadth;
- every reviewed company mapping identifies a specific L4 object and direct product, service, customer, or business evidence;
- revenue or business materiality is disclosed or explicitly recorded as `undisclosed`;
- concept-only companies are excluded from the default beneficiary table;
- stale evidence, unmapped nodes, and unresolved contradictions remain visible;
- research outputs are not used directly for signals, admission, recommendations, or orders.

If a chain supports fewer than eight defensible mappings, the verified smaller set is displayed and the theme remains `研究中`. Coverage must never be padded.

## Wave Execution Order

Wave F and G are designed now but must not bypass unfinished Wave E work.

Recommended execution:

1. close Wave E evidence corrections and unfinished themes;
2. build the shared catalog-first validation and handoff contract once;
3. deliver Wave F in order F1-F5;
4. run a Wave F catalog-ownership, evidence, company-mapping, UI, and port-5174 acceptance checkpoint;
5. deliver Wave G in order G1-G5;
6. run the same Wave G checkpoint and an A-G cross-theme overlap audit.

Within each chain, structural expansion and evidence research may be researched in parallel, but Theme Research cannot be promoted until the canonical L3/L4 structure is validated.

## Acceptance Criteria

The Wave F/G delivery is complete only when:

- the catalog still contains exactly the approved 82 L2 chains unless a separately approved catalog revision changes that number;
- all ten selected IDs are exact members of that catalog;
- G5 is `scientific_instruments`, not `synthetic_biology_biomanufacturing`;
- each selected branch has a validated, readable L3/L4 directory;
- canonical ownership and typed cross-chain relationships pass catalog validation;
- each branch links to exactly one Theme Research record;
- Theme Research uses the catalog nodes as its value-chain structure;
- all ten themes satisfy the source, claim, evidence-gap, and company-mapping gates appropriate to their status;
- company mappings terminate at specific L4 objects and concept associations are separated;
- catalog and Theme Research pages show explicit `未开始`, `研究中`, `已审核`, or `需更新` states;
- company tables use row-click navigation and contain no redundant operation column;
- targeted backend, frontend, registry, catalog, and artifact validation tests pass;
- the real application on port 5174 exposes the directory and linked Theme Research records without loading failures;
- no selected theme duplicates the ownership of an existing A-E chain.

## Non-Goals

- changing the approved 82-chain inventory as part of Wave F/G;
- inventing market-event themes outside the catalog;
- copying nodes between canonical chains;
- selecting a company by keyword association alone;
- forcing unsupported company counts;
- using research priority as an investment rating or trading signal;
- starting Wave F/G implementation before the written implementation plan is separately reviewed;
- completing the other unselected catalog skeletons in this delivery.
