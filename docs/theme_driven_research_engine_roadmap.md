# Theme-driven Research Engine Roadmap

## Phase 9 Status

Phase 9 database productionization completed on 2026-07-11. PostgreSQL is authoritative, Dashboard reads are cut over to DB, controlled review writes are versioned, and export/rollback drills have passed. Artifact mode remains the documented emergency fallback.

Updated: 2026-07-11

## Mission

Theme-driven Research Engine is a theme-first industry research capability for Stock Research Platform, with the existing tech bottleneck workflow as its first major consumer.

It converts research leads into traceable research objects:

```text
short video / report / article / expert view
  -> source traceability
  -> theme decomposition
  -> value capture assessment
  -> bottleneck and localization assessment
  -> company mapping
  -> evidence review
  -> platform display and continuous tracking
```

It does not copy short-video opinions, generate automatic recommendations, produce buy/sell instructions, or treat oral claims as evidence.

## Phase Status

| Phase | Scope | Status | Primary exit condition |
|---|---|---|---|
| 0 | Direction and boundaries | Complete | Mission, evidence principles, and v1 boundaries agreed |
| 1 | Read-only research baseline | Complete | Artifact, loader, CLI, tests, docs, and two sample themes work |
| 1.5 | Source / Claim / Node Review Gate | Complete | Invalid review-state promotion is blocked by validation |
| 2A | AI power source pack | Complete | Public evidence pack and node evidence matrix reviewed |
| 2B | Humanoid robotics source pack | Next | Public evidence pack and node evidence matrix reviewed |
| 3 | Decomposition method library | Complete | Three reusable templates validate against the common schema |
| 4 | Theme node to company mapping | Complete | Every mapping states relationship, materiality, and evidence |
| 5 | Tech bottleneck universe integration | Complete | Crosswalk enriches the existing universe without replacing it |
| 6 | Research priority scoring and review workflow | Complete | Node, company, and evidence-gap priorities are reviewable |
| 7 | Read-only dashboard | Complete | Reviewed/draft/lead/gap states are visible without writeback |
| 8 | Automated ingestion and update | Complete | Extraction feeds a human review queue, never the formal store directly |
| 9 | Database productionization | Complete | Versioned schema, review history, rollback, and APIs are stable |
| 10 | Investment research workflow integration | Complete | Daily Review, Watchlist, and Stock Workspace consume one reviewed context |

## Phase 0: Direction And Boundaries

Purpose: define what the capability solves and what it must not do.

Completed decisions:

- short videos and social posts are research leads, not evidence;
- the engine is not a recommendation or trading signal module;
- source traceability precedes claim acceptance;
- research moves from theme to node to company, not directly from theme to stock;
- the first two samples are AI power and humanoid robotics;
- v1 is artifact-first, read-only, offline, and independent of the production database.

## Phase 1: Read-only Research Baseline

Purpose: prove the minimum data model and loading path.

Delivered:

- JSON artifacts;
- offline loader and validation;
- CLI validate, summary, and show commands;
- source reliability levels `S0-S4`;
- claim evidence status;
- node value capture, bottleneck, localization, supply tightness, and evidence scores;
- AI power and humanoid robotics samples;
- focused pytest coverage and design documentation.

Reference: `docs/theme_decomposition_research_baseline_v1.md`.

## Phase 1.5: Source / Claim / Node Review Gate

Purpose: turn the baseline from a data container into a research quality-control layer.

### Schema additions

`source_item.review_status`:

```text
accepted
needs_full_text
lead_only
rejected
unknown
```

`content_claim.platform_use_status`:

```text
research_lead
draft
reviewed
blocked
```

`theme_node.node_review_status`:

```text
draft
reviewed
needs_evidence
blocked
```

### Mandatory gates

- `S4` sources cannot be `accepted`;
- a claim supported only by `S4` sources cannot be `reviewed`;
- every reviewed claim must have at least one accepted supporting source;
- every reviewed node must have `evidence_strength >= 3`;
- a node with high value capture, high bottleneck, and low evidence strength must enter `high_priority_evidence_gap`;
- rejected sources cannot support reviewed claims or nodes;
- all state transitions must produce deterministic validation errors.

### Deliverables

- review-status fields in both sample artifacts;
- gate validator and stable error codes;
- evidence-gap summary output;
- pytest coverage for every invalid transition;
- migration note for the artifact schema version.

Exit condition: both sample themes pass the gate, and every prohibited state is covered by a failing fixture test.

Implementation result:

- both sample artifacts migrated to `theme_decomposition_v1_5`;
- source, claim, and node review states are required;
- stable gate error codes are exposed by loader and CLI;
- high-priority evidence gaps are included in summary output;
- prohibited states and sample artifacts are covered by focused pytest;
- migration details are recorded in `docs/theme_decomposition_artifact_schema_v1_5_migration.md`.

## Phase 2: Real Source Packs

Purpose: replace placeholder and lead-level evidence with public, traceable source packs.

### Phase 2A: AI Power

Research questions:

- Is AI electricity demand supported by public data?
- Where are the actual power-delivery constraints?
- Which nodes gain value through BOM share, scarcity, delivery lead time, certification, or integration control?
- Which nodes are genuine localization bottlenecks and which are ordinary cyclical products?

Target source types:

- J.P. Morgan public articles and Eye on the Market PDFs;
- public secondary reporting that clearly cites the original source;
- domestic broker reports on power equipment, liquid cooling, and HVDC;
- company filings and annual reports;
- public industry and power-system data.

Deliverables:

```text
ai_power_source_pack_v1.json
ai_power_claim_review_v1.json
ai_power_node_evidence_matrix_v1.json
```

Implementation result:

- seven public official or institutional sources are accepted with section-level locators and explicit limitations;
- LBNL, IEA, OCP, and domestic broker full-text targets remain visibly separated as `needs_full_text`;
- five claims are reviewed, two blanket value-capture claims are blocked, and localization remains a research lead;
- all 13 canonical nodes are covered by the evidence matrix;
- grid connection, HVDC technical route, AI server integration, and liquid cooling are upgraded to reviewed node evidence;
- transformer, switchgear, UPS, copper, SiC/GaN, EPC, and other unresolved economics remain evidence gaps;
- validation and findings are documented in `docs/ai_power_source_pack_v1.md`.

### Phase 2B: Humanoid Robotics

Research questions:

- Which nodes have high value content and technical barriers?
- Which nodes have meaningful localization gaps?
- Which nodes are mainly narrative or concept exposure?
- How should roller screws, reducers, motors, encoders, force sensors, and dexterous hands be prioritized?

Target source types:

- full-text broker decomposition reports;
- official Tesla Optimus and other manufacturer materials;
- overseas component-company materials;
- domestic listed-company filings, announcements, and annual reports;
- traceable BOM and industry-chain materials.

Deliverables:

```text
humanoid_robotics_source_pack_v1.json
humanoid_robotics_claim_review_v1.json
humanoid_robotics_node_evidence_matrix_v1.json
```

Exit condition: reviewed claims and node scores can be traced to excerpt-level evidence, and S2-S4 leads remain visibly separated from accepted sources.

## Phase 3: Decomposition Method Library

Purpose: make theme decomposition reusable beyond the first two samples.

Templates:

```text
decomposition_templates/
  system_bottleneck_template.json
  head_to_toe_template.json
  manufacturing_process_template.json
```

System bottleneck template:

```text
demand shock -> system bottleneck -> chain nodes -> supply constraints
-> value migration -> bottleneck nodes -> company mapping
```

Head-to-toe template:

```text
whole-system structure -> functional systems -> core components
-> technical routes -> BOM value -> import dependency -> localization
```

Manufacturing-process template:

```text
process flow -> key equipment -> key materials -> yield bottleneck
-> overseas leaders -> localization -> customer verification cycle
```

Exit condition: a new theme can be initialized from a template without adding ad hoc fields or code paths.

Implementation result:

- three versioned templates use one common `decomposition_template_v1` schema;
- every template contains eight ordered research steps, quality gates, source requirements, and seven node archetypes;
- one standard-library loader validates all template families;
- one generic initializer produces valid `theme_decomposition_v1_5` draft artifacts;
- AI compute, humanoid robotics, and semiconductor-equipment initialization paths are verified through the existing theme loader;
- AI power and humanoid robotics are registered as examples of the system-bottleneck and head-to-toe families;
- usage and extension rules are documented in `docs/decomposition_method_library_v1.md`.

## Phase 4: Theme Node To Company Mapping

Purpose: map companies to specific industry-chain roles without turning the module into a recommendation engine.

Required fields:

```text
company_code
company_name
market
mapped_node_id
mapping_type
confidence
evidence_ids
revenue_relevance
bottleneck_relevance
notes
```

Allowed mapping types:

```text
direct_product
component_supplier
equipment_supplier
material_supplier
system_integrator
downstream_customer
```

Rules:

- report mention alone is not enough;
- the node relationship must be explicit;
- mapping must have evidence;
- primary business, concept exposure, and reserve-stage business must be separated;
- revenue relevance and business materiality must remain independent from theme popularity.

Implementation result:

- a common `theme_company_mapping_v1` artifact schema links mappings to canonical theme nodes;
- excerpt-level evidence items separate product relationship, revenue materiality, customer validation, and company mentions;
- every mapping status requires evidence, and each artifact owns its theme, sources, evidence, and mappings without cross-artifact borrowing;
- reviewed mappings require accepted S0/S1 direct-relationship evidence, matching company/node scope, and confidence of at least 0.7;
- reviewed materiality claims, including limited revenue claims, require accepted revenue-materiality evidence; weaker sources can remain supplemental but cannot satisfy a review gate;
- primary business, concept exposure, and reserve-stage activity are distinct validated states;
- broader segment revenue cannot be assigned automatically to a narrower theme node;
- theme/company lookup commands resolve evidence records and source metadata instead of returning evidence IDs alone;
- the first AI-power sample maps Envicool, Kehua Data, Oulutong, and Zhongheng Electric using 2025 CNINFO annual reports;
- the loader, CLI, quality gates, and sample semantics are documented in `docs/theme_company_mapping_v1.md`.

## Phase 5: Tech Bottleneck Universe Integration

Purpose: enrich the current authoritative review-universe snapshot with industry-chain context without replacing its evidence or review history.

Crosswalk fields:

```text
theme_node_id
company_code
existing_review_universe_id
existing_evidence_ids
new_theme_evidence_ids
confidence
review_status
```

Target model:

```text
theme -> node -> bottleneck problem -> company -> evidence
```

Exit condition: the crosswalk is read-only, reversible, and does not change existing admission or review decisions.

Implementation result:

- a versioned `theme_tech_bottleneck_crosswalk_v1` artifact remains separate from the current authoritative review-universe dataset and Phase 4 mapping artifacts;
- checkout-independent deterministic IDs make existing universe, evidence, and source CSV rows addressable without modifying them;
- authoritative path and CSV-schema gates prevent an artifact from substituting a different review-universe input dataset;
- SHA-256 snapshot checks reject silent upstream drift;
- Envicool and Kehua Data are linked to their existing pending-review rows with evidence from both systems;
- Oulutong and Zhongheng Electric are explicit coverage gaps because they are absent from the existing universe; no admission is inferred;
- all four Phase 4 AI-power mappings must be represented exactly once as a link or gap;
- DB, CSV, manual-review, admission, signal, and quality-pool writes remain disabled;
- the loader, CLI, stable IDs, validation gates, and boundaries are documented in `docs/theme_tech_bottleneck_crosswalk_v1.md`.

## Phase 6: Priority Scoring And Human Review

Purpose: rank research work, not trades.

Dimensions:

```text
value_capture_score
bottleneck_score
localization_gap_score
supply_tightness_score
evidence_strength
company_relevance_score
business_materiality
```

Outputs:

```text
Theme Node Priority
Company Research Priority
Evidence Gap Priority
```

Examples:

- high value capture + high bottleneck + low evidence = evidence collection priority;
- high value capture + high bottleneck + strong evidence + high company relevance = deep-research priority.

Implementation result:

- a versioned `theme_research_priority_policy_v1` artifact owns all weights, thresholds, materiality conversion, allowed dimensions, forbidden dimensions, and guardrails;
- all 34 current theme nodes receive transparent deep-research and evidence-gap scores with component-level explanations;
- all four Phase 4 company mappings receive a company research score based only on node structure, evidence, mapping relevance, and business materiality;
- P5 linked/coverage-gap status affects queue routing but never changes the merit score;
- current outputs contain 15 evidence-collection nodes, 2 deep-research nodes, 17 monitor nodes, and 4 company priorities;
- a 21-item read-only queue uses `pending_human_review` and keeps existing tech-bottleneck review context separate;
- price, valuation, return, momentum, freshness, low-position, technical-signal, and entry-timing inputs are forbidden;
- signal, admission, automatic reviewer decision, and database writes remain disabled;
- formulas, score interpretation, queue actions, CLI commands, and boundaries are documented in `docs/theme_research_priority_v1.md`.

## Phase 7: Read-only Dashboard

Purpose: expose reviewed research state after the model and gates are stable.

Initial routes:

```text
/theme-research
/theme-research/:theme_id
/theme-research/:theme_id/nodes
/theme-research/:theme_id/sources
/theme-research/:theme_id/companies
```

Initial presentation should be table-first, showing reviewed, draft, research-lead, blocked, and evidence-gap states. A graph view is deferred until the table model proves useful.

Implementation result:

- the existing Dashboard now has a combined `主题研究与产业目录` navigation entry and route-backed workspace, while `卡脖子复盘` remains a separate primary navigation entry and stock-centered review workspace;
- `/theme-research` provides a cross-theme table and theme detail uses route-backed overview, nodes, sources, and companies tabs;
- six GET-only APIs join validated P1-P6 packages without network, artifact, DB, admission, signal, or review-decision writes;
- nodes, source reliability, claim evidence state, company priorities, crosswalk coverage gaps, and existing review context remain distinguishable;
- company rows hand off to the existing tech-bottleneck stock route using `source=theme_research` without copying review state;
- the table-first layout is responsive, uses inner table scrolling on mobile, and defers graph visualization;
- backend, frontend, production build, and desktop/mobile Playwright acceptance are documented in `docs/theme_research_dashboard_v1.md`.

## Phase 8: Automated Ingestion And Update

Purpose: reduce manual preparation while preserving human review.

```text
source ingest -> claim extraction -> theme/node matching
-> evidence classification -> human review queue -> artifact/DB update
```

Inputs may include manually recorded video claims, report PDFs, company filings, news, public articles, and Daily Review theme leads. AI extraction must never write directly into the formal reviewed store.

Implementation result:

- four local-only adapters cover manual claim JSON, Markdown/TXT/HTML, Docling-parsed PDF, and existing exported records;
- normalized content, source metadata, adapter provenance, and SHA-256 fingerprints produce deterministic, idempotent run IDs;
- `rule_based_sentence_v1` extracts staging-only claims and `theme_node_matcher_v1` suggests existing theme/node links without changing the node graph;
- every run is a versioned, checksum-protected artifact package with an append-only human review ledger;
- S4 sources cannot be accepted, automated claims cannot start as reviewed, and reviewed claims require an accepted non-S4 source;
- promotion requires an explicit reviewer trail and optimistic canonical SHA-256, then validates, backs up, and atomically replaces only the target theme artifact;
- promotion can add sources and claims only; nodes, scores, assessments, company mappings, crosswalks, priority policies, DB state, and signal/admission state remain unchanged;
- generated runs stay local and the checked-in S4 sample proves that oral/video content remains a lead;
- CLI, operating procedure, failure handling, and boundaries are documented in `docs/theme_research_ingestion_v1.md`.

## Phase 9: Database Productionization

Purpose: migrate only after the artifact schema and review gates are stable.

Candidate tables:

```text
themes
theme_nodes
source_items
content_claims
value_capture_assessments
company_mappings
evidence_reviews
review_events
```

Production requirements:

- artifact and schema versioning;
- review and state-transition history;
- evidence provenance;
- human confirmation;
- rollback;
- read APIs and controlled write APIs.

Implementation result:

- PostgreSQL is authoritative and the Dashboard reads through `THEME_RESEARCH_READ_SOURCE=db`;
- owner, migration, runtime-group, and runtime-login roles separate schema ownership from application reads;
- canonical objects, relationships, revisions, review events, snapshots, imports, and store generation are versioned;
- source, claim, and node reviews use optimistic row versions, idempotency keys, immutable history, and evidence gates;
- artifact/DB semantic parity, export, rollback, runtime privilege isolation, and production cutover were verified;
- artifact mode remains an explicit emergency read fallback, not a dual-write path;
- operations and recovery are documented in `docs/theme_research_database_v1.md`.

## Phase 10: Research Workflow Integration

Purpose: make reviewed theme context available to Daily Review, Watchlist, tech bottleneck research, company research, and theme tracking. Phase 10 provides conservative anomaly context and reviewed-source update reminders inside these workflows; it does not claim automated causal attribution or add a separate push-reminder scheduler.

The target daily-review answer is:

```text
Which theme does the company belong to?
Which industry-chain node does it map to?
What are the node's value-capture and bottleneck scores?
What source or claim changed recently?
Is the move theme-driven or company-fundamental-driven?
```

Implementation result:

- one PostgreSQL-backed `Theme Research Context Service` supplies all workflow consumers;
- company context fails closed unless the theme, company mapping, and node are reviewed and mapping evidence uses accepted sources;
- Daily Review reports reviewed theme coverage, mapped companies, recent reviewed changes, evidence gaps, and incomplete evidence tracks;
- Watchlist rows retain their original ordering and signal fields while adding compact theme/node context;
- Stock Workspace shows the theme, mapped node, value-capture and bottleneck scores, business relationship, and evidence counts;
- `GET /api/assets/:asset_id/theme-research-context` and `GET /api/research/theme-decomposition/updates` expose the same read model;
- all workflow payloads remain `research_only=true`, `used_for_signal=false`, and `used_for_admission=false`;
- driver assessment remains conservative and uses `mixed_or_uncertain` or `insufficient_evidence` when causality is not proven;
- Daily Review's recent reviewed changes are the v1 report-update reminder surface; proactive push delivery is outside Phase 10;
- Phase 2B humanoid robotics remains an explicit evidence gap and is excluded from reviewed workflow context;
- `theme-research verify-p1-p10` produces requirement-level JSON and Markdown verification reports.

## Near-term Execution Order

Phases 9 and 10 are complete for reviewed research objects. The next evidence task is Phase 2B: build the humanoid-robotics public source pack through the Phase 8 human-review queue. Until that evidence track is complete, its sample structure remains visible in Theme Research but cannot enter Daily Review, Watchlist, or Stock Workspace as reviewed context.
