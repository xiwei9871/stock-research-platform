# Five Priority Industry Chains As Deep Theme Research Design

Date: 2026-07-14
Status: approved

## Goal

Turn five high-priority technology industry chains into evidence-backed, readable Theme Research packages that answer how the value chain works, where value is captured, which listed companies are exposed, why they may benefit, and what evidence supports each conclusion.

The Technology Industry Catalog remains the structural directory and discovery surface. Deep research belongs to the existing Theme Research domain so that sources, claims, node assessments, company mappings, review gates, update history, and research-only guardrails use one authoritative model.

## Selected Industry Chains

The first deep-research batch contains these five chains:

| Priority | Catalog chain | Theme Research record | Current foundation |
| --- | --- | --- | --- |
| 1 | `ai_data_center_power` | reuse `ai_power_value_capture_v1` | Existing reviewed theme, source pack, claim review, node evidence matrix, and four reviewed company mappings |
| 2 | `semiconductor_manufacturing_equipment` | create `semiconductor_manufacturing_equipment_value_chain_v1` | Detailed manufacturing-process tree with ten L3 process families and investment-relevant L4 equipment nodes |
| 3 | `humanoid_robots_embodied_intelligence` | reuse and complete `humanoid_robotics_head_to_toe_v1` | Existing draft theme and twelve L3 system families; company and evidence coverage remains incomplete |
| 4 | `ai_compute_infrastructure` | create `ai_compute_infrastructure_value_chain_v1` | Approved L2 catalog scope; requires a complete system-architecture decomposition and evidence package |
| 5 | `new_energy_storage` | create `new_energy_storage_value_chain_v1` | Approved L2 catalog scope; requires decomposition across cells, power conversion, control, safety, integration, and operation |

The selection balances immediate delivery feasibility, A-share research relevance, technology bottlenecks, industrial-policy durability, and coverage across semiconductors, AI infrastructure, advanced equipment, and energy systems.

## Product Boundary

### Technology Industry Catalog owns

- L1 sector and L2 industry-chain identity;
- canonical L3/L4 taxonomy and cross-chain ownership;
- chain kind, decomposition method, scope, exclusions, aliases, and structural status;
- typed dependencies and application-role composition;
- the link from a catalog chain/node to its Theme Research record/node;
- structural completeness and deep-research availability status.

### Theme Research owns

- the readable investment-research summary;
- value-chain interpretation and value-capture assessment;
- sources, claims, evidence states, and evidence gaps;
- catalysts, risks, bottlenecks, localization gaps, and key metrics;
- company mappings, product relationships, business materiality, and confidence;
- human review state, generation/version history, exports, and rollback;
- links into Stock Workspace and existing research workflows.

The catalog must not copy company mappings, claims, or source records. Theme Research must not redefine the canonical industry taxonomy. The two domains join through explicit `chain_id`, `theme_id`, and node-link records.

## Navigation And User Flow

The existing routes remain authoritative:

- `/theme-research/catalog` lists the complete Technology Industry Catalog;
- `/theme-research/catalog/:chain_id` shows structural catalog detail;
- `/theme-research/:theme_id` and its existing subroutes show deep research.

For each selected chain, the catalog index and chain detail show a compact deep-research status:

- `未开始`: no linked Theme Research record;
- `研究中`: linked theme is `draft` or has unresolved evidence gates;
- `已审核`: linked theme passed the existing Theme Research review gates;
- `需更新`: reviewed research exists but its evidence freshness policy is breached.

The catalog chain page shows only a concise research card: theme title, one-paragraph summary, status, source count, reviewed-company count, evidence-gap count, and last update time. Its primary action is `进入深度研究`, which opens the linked Theme Research page. The full research content is never rendered a second time inside the catalog.

The Theme Research index marks these five records with a `产业链深度研究` badge and displays their catalog chain names. Users can search them alongside existing themes without introducing another primary workspace.

## Deep Theme Page Contract

Every selected theme must provide the following readable sections.

### 1. One-page research conclusion

- what the chain produces or enables;
- the present industrial stage;
- the central supply/demand or technology conflict;
- the most important value-capture nodes;
- the strongest current catalysts and risks;
- a concise statement of what remains unproven.

### 2. Value-chain map

Render the canonical catalog hierarchy as an ordered research flow rather than a flat technical table. Each L3 stage shows its purpose, upstream inputs, downstream users, and important L4 products or services. Typed edges explain material, equipment, energy, data, or service dependencies.

Every investment-relevant L4 node reports:

- node description and role in the chain;
- `value_capture_score`;
- `bottleneck_score`;
- `localization_gap_score`;
- `supply_tightness_score`;
- `evidence_strength`;
- key operating or technical metrics;
- major technical routes;
- reviewed claims and evidence gaps;
- mapped companies.

### 3. Profit pools and competitive barriers

Explain why value may accumulate at specific nodes. The explanation must distinguish pricing power, qualification barriers, process know-how, scale, switching cost, capacity scarcity, regulation, customer concentration, and service lock-in. A score without a sourced explanation remains an evidence gap.

### 4. Catalysts, validation signals, and risks

Claims are grouped into demand, policy, technology, capacity, pricing, localization, and competition. Each catalyst has an observable validation signal and each risk states what evidence would invalidate the current thesis.

### 5. Company-beneficiary map

Company rows are grouped into four research tiers:

- `核心受益`: direct product or service, meaningful business exposure, and reviewed evidence;
- `弹性受益`: direct exposure with smaller current materiality but credible incremental sensitivity;
- `间接受益`: enabling material, equipment, software, or service exposure with a longer transmission path;
- `概念关联`: association exists but product, customer, revenue, or order evidence is insufficient.

Only the first three tiers appear in the default beneficiary table. `概念关联` stays in a separate evidence-gap list and is never presented as a reviewed beneficiary.

Each company row must show:

- company code and name;
- mapped canonical node and Theme Research node;
- product or service supplied;
- mapping type and business stage;
- business materiality and disclosed revenue relevance;
- relationship summary explaining the benefit transmission path;
- confidence and bottleneck relevance;
- supporting evidence and publication dates;
- current review status and unresolved gaps;
- link to Stock Workspace.

The beneficiary tier is a deterministic read-model classification based on mapping type, business materiality, revenue relevance, confidence, bottleneck relevance, and evidence status. It is not stored as an unsupported analyst label.

### 6. Sources and evidence

Sources retain the existing Theme Research reliability and review semantics. Preferred evidence order is:

1. company filings, annual/interim reports, official product material, and investor-relations records;
2. government, regulator, standards body, industry association, customer, or supplier primary material;
3. high-quality industry and broker research with identifiable title and date;
4. reputable media used only for corroboration or lead generation;
5. social, video, or oral claims retained only as unverified research leads.

Every material company mapping requires first-party evidence for the product/business relationship and evidence for business materiality or an explicit `undisclosed` state. Every reviewed node claim must reference at least one accepted source. Unsupported scores cannot pass review.

### 7. Evidence gaps and update history

The page explicitly lists missing sources, stale evidence, unverified company relationships, unquantified revenue exposure, and unmapped catalog nodes. Version and update history remains visible through the existing Theme Research generation and review model.

## Data Architecture

The existing Theme Research source, claim, node, company-mapping, evidence, review, database, snapshot, and read-service models remain authoritative.

Implementation adds adapters rather than a parallel research schema:

- catalog-to-theme link artifacts for all five chains;
- catalog-node to theme-node mappings with explicit unmapped-node reporting;
- a catalog-aware Theme Research read-model summary;
- derived beneficiary tiers and evidence-freshness status;
- deep-research coverage metrics on the catalog API;
- additional source packs, claim reviews, node evidence matrices, and company mapping artifacts for the five themes;
- controlled import into the PostgreSQL Theme Research store using the existing ingestion and review workflow.

Application-theme chains may compose canonical catalog nodes, but company mappings stay on the owned canonical or reviewed Theme Research nodes. The UI aggregates mappings through explicit references and never duplicates them across chains.

## Theme-specific Research Scope

### AI Data Center Power

Retain the existing eleven-stage infrastructure decomposition. Complete the readable value-flow narrative from capacity planning and grid access through backup power, UPS/DC conversion, room/rack distribution, server-board power, liquid cooling, EMS, EPC, commissioning, and operations. Revalidate existing reviewed mappings and expand coverage only when company-primary evidence supports it.

### Semiconductor Manufacturing Equipment

Cover lithography/patterning, etch, thin-film deposition/epitaxy, thermal processing/doping, clean/wet processing, CMP, inspection/metrology/process control, wafer handling/fab automation, vacuum/gas/fluid control, and facilities/pollution control. Company research must separate direct tool vendors from components, subsystems, materials, and service providers.

### Humanoid Robots And Embodied Intelligence

Complete the existing head-to-toe architecture across embodied-intelligence software, motion control, training/simulation, perception, compute/control hardware, rotary and linear actuators, dexterous hands, lower-limb locomotion, body structure, energy/thermal management, and manufacturing/test/integration. Draft or social supply-chain claims remain outside the reviewed beneficiary list until verified.

### AI Compute Infrastructure

Decompose accelerators and compute boards, servers and racks, high-speed interconnect, storage, cluster networking, power and cooling dependencies, orchestration/system software, data-center delivery, and operations. Avoid duplicating the AI Data Center Power theme: power and cooling appear as linked dependencies, while this theme owns compute-system architecture, deployment, and utilization economics.

### New Energy Storage

Decompose storage cells and materials, battery modules/packs, PCS, BMS, EMS, thermal management, fire protection, enclosures, transformers/switchgear, system integration, EPC, grid connection, operation/maintenance, and market participation. Distinguish cell manufacturing economics from system integration and power-market service economics.

## Coverage And Review Gates

A selected theme is not `已审核` until all of these conditions are true:

- all L3 stages have readable descriptions, ordered flow, and catalog links;
- every investment-relevant L4 node has a research assessment or an explicit evidence-gap state;
- at least ten accepted sources are present, including at least four primary or first-party sources;
- at least ten structured claims cover value capture, catalysts, risks, and competitive barriers;
- every reviewed claim has an accepted source;
- at least eight evidence-backed A-share company mappings are present when the chain supports that breadth;
- every reviewed company mapping has product/business evidence and a materiality state;
- concept-only candidates are separated from reviewed beneficiaries;
- unresolved evidence gaps and stale evidence are visible;
- no research output is used directly for signal generation, admission, recommendation, or order actions.

If a chain cannot support eight reviewed company mappings, the theme remains `研究中` and reports the verified smaller set rather than padding coverage with concept associations.

## API And Frontend Changes

The catalog APIs add deep-research summary fields derived from Theme Research:

- linked `theme_id` and title;
- research status and freshness status;
- source, claim, reviewed-company, and evidence-gap counts;
- last reviewed/update time;
- Theme Research route.

Theme Research list/detail responses add catalog context and derived beneficiary tiers without changing existing route compatibility. The frontend adds:

- deep-research status and entry action in catalog list/detail;
- `产业链深度研究` identity in Theme Research;
- a readable value-chain view;
- profit-pool/barrier and catalyst/risk sections;
- beneficiary-tier filters and evidence details;
- explicit incomplete, stale, and concept-only states.

All UI remains read-only. Review, promotion, import, export, and rollback continue through the existing controlled Theme Research workflows.

## Delivery Order

1. Establish the shared catalog-to-theme adapter, deep-research contract, beneficiary classifier, API fields, and frontend sections.
2. Upgrade AI Data Center Power as the reference implementation.
3. Build Semiconductor Manufacturing Equipment.
4. Complete Humanoid Robots And Embodied Intelligence.
5. Build AI Compute Infrastructure.
6. Build New Energy Storage.
7. Run cross-theme coverage verification, database import/review, dashboard regression, browser acceptance, and real 5174 validation.

Each theme is delivered through the same schema and gates. Later themes must not introduce one-off page sections or incompatible company scoring.

## Verification And Acceptance

Completion requires evidence that:

- the catalog still exposes all 82 approved L2 chains and remains usable as a directory;
- exactly the selected five chains expose a deep-research entry and status;
- the five Theme Research records are visible in the existing Theme Research workspace;
- every record renders all seven required readable sections;
- catalog nodes, theme nodes, claims, sources, and company mappings pass deterministic validation;
- beneficiary tiers match their source mapping/materiality/evidence inputs;
- concept-only companies never appear in the default reviewed-beneficiary table;
- unknown or incomplete chains show explicit states rather than blank pages;
- targeted backend, frontend, database integration, build, and Playwright suites pass;
- desktop and mobile views have no page-level horizontal overflow;
- the authenticated real application on port 5174 serves the five research themes and their catalog entry points;
- the final branch is clean, pushed, and documented.

## Non-goals

- providing buy/sell recommendations, target prices, or trading signals;
- treating catalog membership or keyword matching as company-beneficiary evidence;
- forcing unsupported company counts to satisfy a coverage target;
- copying full Theme Research content into the catalog;
- completing all 82 chains in this delivery;
- adding write controls to the dashboard;
- replacing existing Theme Research review and PostgreSQL productionization workflows.
