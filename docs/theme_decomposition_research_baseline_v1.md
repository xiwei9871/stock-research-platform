# Theme Decomposition Research Baseline v1

## 1. Why This Module Exists

Short videos, public articles, and research reports can surface useful industry-research prompts, but they are not equally reliable. This module turns a prompt such as "AI power value capture" or "humanoid robotics from head to toe" into a read-only, traceable research baseline.

The goal is not stock recommendation. The goal is to preserve the research method:

- identify the source;
- classify evidence quality;
- extract claims without over-trusting them;
- decompose a theme into industry-chain nodes;
- score value capture and bottleneck risk at node level;
- leave company mapping empty until source-backed evidence exists.

## 2. Relationship With Tech Bottleneck Research

The current tech bottleneck flow is mostly stock and review-universe oriented. This baseline adds a theme-first layer:

`theme -> theme_node -> bottleneck/value_capture/localization_gap -> company mapping -> evidence`

It does not replace existing tech bottleneck data, candidate pools, manual review flows, or dashboard datasets. v1 is a read-only artifact layer that can later feed tech bottleneck review workflows after evidence and company mapping are validated.

## 3. Content Source Intelligence Evidence Levels

`source_item.reliability_level` uses five levels:

- `S0`: original full text is available, such as a formal broker PDF, company filing, official announcement, or official white paper.
- `S1`: official public article or official PDF, but not a full sell-side report.
- `S2`: official or public reference to an institutional report where the full report is not attached.
- `S3`: media secondary reporting, screenshots, or reposted summaries.
- `S4`: short-video oral claim, social-post claim, or unverifiable statement.

Rules:

- Short videos are research clues only. They cannot be formal evidence.
- Closed-door or gated research cannot be treated as `S0` unless the platform has the full text.
- Every platform claim must trace back to a `source_item`.
- `reliability_level` describes the source; `content_claim.evidence_status` describes whether the claim is verified.

## 4. Theme Decomposition Engine Flow

The v1 decomposition process is:

1. Define the theme and theme type.
2. Record source items before extracting claims.
3. Convert content into `content_claim` records.
4. Split the theme into `theme_node` industry-chain nodes.
5. Score each node from 0 to 5 on value capture, bottleneck, localization gap, supply tightness, and evidence strength.
6. Add `value_capture_assessment` records that distinguish the value basis:
   - `BOM_share`
   - `ASP`
   - `gross_margin`
   - `scarcity`
   - `integration_control`
   - `customer_certification`
   - `capacity_constraint`
   - `technology_barrier`
7. Leave company mapping empty until filings, official product evidence, or reliable reports support it.

## 5. AI Power Value Capture Sample

Artifact:

`artifacts/theme_decomposition/ai_power_value_capture_v1.json`

The sample path is:

AI training and inference demand growth -> AI server and rack power-density growth -> data-center power-delivery constraints -> grid connection, transformer, switchgear, UPS, HVDC, server power supply, rack distribution, liquid cooling, copper interconnect, SiC/GaN, EPC, and server integration.

Phase 2A now explicitly separates:

- accepted DOE, J.P. Morgan, and NVIDIA public evidence;
- inaccessible original reports and exact OCP/broker full-text targets;
- oral short-video clues;
- unadopted social stock mappings.

The detailed source, claim, and node review is documented in `docs/ai_power_source_pack_v1.md`.

## 6. Humanoid Robotics Sample

Artifact:

`artifacts/theme_decomposition/humanoid_robotics_head_to_toe_v1.json`

The sample path is:

body structure -> functional systems -> components -> technical route -> value capture -> bottleneck -> localization gap -> company mapping evidence queue.

Nodes include head vision, onboard compute, torso, arm actuator, dexterous hand, hip/knee/ankle joints, frameless motor, harmonic reducer, planetary roller screw, encoder, force sensors, tactile sensors, IMU, battery/BMS, wiring harness, controller, bearing, and lightweight materials.

## 7. Future Stock And Company Mapping

v1 keeps `domestic_players`, `overseas_leaders`, and `related_stock_codes` as arrays, but leaves them mostly empty. Future mapping should require at least one of:

- company filing or annual report excerpt;
- official product or customer certification evidence;
- reliable full-text broker report;
- verified supply-chain article with original source reference.

Company mapping should be added at node level, not theme level. A company must state which node it maps to and why.

## 8. v1 Boundaries

v1 is intentionally narrow:

- no DB writes;
- no network access;
- no automatic stock recommendation;
- no dashboard frontend;
- no mutation of existing tech bottleneck data;
- no claim promotion from short video to verified evidence;
- no automated company mapping.

The loader only reads JSON artifacts and validates required fields, enum values, score ranges, and basic references.

Phase 1.5 adds a read-only review gate without changing these boundaries. Source, claim, and node review states are now required, and invalid reviewed states are rejected with stable error codes. See `docs/theme_decomposition_artifact_schema_v1_5_migration.md`.

## 9. Roadmap

The authoritative multi-phase roadmap is documented in:

`docs/theme_driven_research_engine_roadmap.md`

Phase 1.5, Phase 2A, Phase 3, Phase 4, Phase 5, Phase 6, the Phase 7 read-only Dashboard, and the Phase 8 artifact-first ingestion/review boundary are complete. Phase 2B, the humanoid robotics source pack, remains an unfinished evidence task. Database productionization follows only after Phase 8 operating history stabilizes the schema and transitions.

The reusable method library and generic theme initializer are documented in `docs/decomposition_method_library_v1.md`.

The evidence-backed company-mapping schema and AI-power samples are documented in `docs/theme_company_mapping_v1.md`.

The reversible crosswalk to the existing tech-bottleneck review universe is documented in `docs/theme_tech_bottleneck_crosswalk_v1.md`.

The research-priority policy and pending-human-review queue are documented in `docs/theme_research_priority_v1.md`.

The Phase 7 read-only theme index, route-backed detail workspace, API contract, and tech-bottleneck stock handoff are documented in `docs/theme_research_dashboard_v1.md`.

The Phase 8 local adapters, immutable run package, append-only review ledger, evidence gates, and atomic source/claim promotion are documented in `docs/theme_research_ingestion_v1.md`.

## Usage

Validate artifacts:

```bash
.venv/bin/python -m stock_research.theme_decomposition validate
```

Print summary:

```bash
.venv/bin/stock-research theme-decomposition summary
```

Show one theme:

```bash
.venv/bin/stock-research theme-decomposition show --theme ai_power_value_capture_v1
```

Validate the AI power evidence pack:

```bash
.venv/bin/python -m stock_research.ai_power_source_pack validate
```

Print the AI power evidence summary:

```bash
.venv/bin/python -m stock_research.ai_power_source_pack summary
```

Validate the decomposition method library:

```bash
.venv/bin/python -m stock_research.decomposition_templates validate
```

Initialize a new draft theme:

```bash
.venv/bin/python -m stock_research.decomposition_templates initialize \
  --template manufacturing_process_v1 \
  --theme-id semiconductor_process_example_v1 \
  --theme-name "Semiconductor Process Example" \
  --theme-type semiconductor_equipment \
  --last-updated 2026-07-10
```

Validate company mappings:

```bash
.venv/bin/python -m stock_research.theme_company_mapping validate
```

Show one company's theme-node mappings:

```bash
.venv/bin/python -m stock_research.theme_company_mapping show-company \
  --company-code 300870.SZ
```

Validate the tech-bottleneck crosswalk:

```bash
.venv/bin/python -m stock_research.theme_tech_bottleneck_crosswalk validate
```

Show one linked company with both evidence systems:

```bash
.venv/bin/python -m stock_research.theme_tech_bottleneck_crosswalk show-company \
  --company-code 002837.SZ
```

List Phase 4 mappings absent from the existing review universe:

```bash
.venv/bin/python -m stock_research.theme_tech_bottleneck_crosswalk coverage-gaps
```

Validate Phase 6 research priorities:

```bash
.venv/bin/python -m stock_research.theme_research_priority validate
```

Show the pending human review queue:

```bash
.venv/bin/python -m stock_research.theme_research_priority review-queue
```
