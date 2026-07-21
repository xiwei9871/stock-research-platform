# Stage A Industry Cognition and Evidence Synthesis Baseline v1 Design

## 1. Purpose and baseline

This stage builds and executes **产业认知、技术理解、因果分析与判断能力基线 v1** for the AI Compute PCB project.

It binds read-only to:

- commit `7280ba71b1694f1ac5938d8be258b9803dfc285e`;
- checkpoint `acquisition_checkpoint:a5f7627d8726c9405ba67a75` and canonical hash `a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e`;
- the existing Stage A scope correction;
- ER01–ER05;
- existing candidates, attempts, raw artifacts, normalized documents, provenance, failures, duplicate/common-origin classifications and unknown dates.

No upstream object is modified or regenerated.

## 2. Non-goals

This stage does not create or authorize company mapping, an equity universe, company exposure/capability assessment, stock analysis, valuation, scoring, recommendation, signal, admission, portfolio, watchlist, strategy, Dashboard/API/database writes, Stage A2, Stage B, automatic acquisition or another theme.

Global entities remain `global_industry_reference` sources only.

## 3. Architecture

```text
existing normalized evidence
        ↓ immutable section-level references
industry cognition package
        ↓ fixed canonical renderer
deterministic analysis report
        ↓ deterministic validator and capability rules
deterministic cognition audit
```

- Package is the only cognition source of truth.
- Report is a human-readable package projection.
- Audit is recomputed coverage, boundary and consistency output.
- Schema/validator fail closed on grounding, scope and capability errors.

Report and audit cannot introduce claims, mechanisms, edges or judgments.

## 4. Files

```text
artifacts/research_projects/v2_1/
├── schema/industry_cognition_baseline_v2_5.schema.json
├── analysis/ai_pcb_industry_cognition_package_v1.json
├── analysis/ai_pcb_industry_cognition_audit_v1.json
└── reports/ai_pcb_industry_cognition_report_v1.md

src/stock_research/research_project_v2_1/
├── cognition.py
├── cognition_render.py
└── cognition_audit.py
```

Also add focused tests, minimal CLI wiring, a concise method document and an exact allowlist. Do not persist per-object claim/mechanism/edge files.

## 5. Schema discriminator and versions

One backward-compatible Schema 2.5.0 supports:

```text
artifact_type = industry_cognition_package
artifact_type = industry_cognition_audit
```

Conditional branches prevent field leakage. Package cannot contain computed capability/audit results. Audit cannot contain new cognition objects.

Manage separately:

- `schema_version`;
- `renderer_version`;
- `capability_rule_version`;
- `domain_matrix_version`;
- `audit_question_set_version`.

## 6. Package structure

```text
industry_cognition_package
├── identity_and_versions
├── baseline_bindings
├── research_framing
├── research_question_tree
├── evidence_inventory
├── er_assessments
├── claim_assessment_ledger
├── grounded_system_model
├── unverified_system_extensions
├── evidence_grounded_mechanisms
├── unverified_mechanism_skeletons
├── grounded_causal_edges
├── hypothesized_causal_edges
├── technology_route_comparisons
├── limited_system_bottleneck_judgments
├── value_change_hypotheses
├── contradictions_and_uncertainties
├── evidence_gap_referrals
└── verification_and_falsification
```

Package is canonical JSON with a self-excluding RFC 8785 SHA-256 hash. It stores cognition inputs, not a freely declared capability rating.

## 7. Framing, questions and system model

Framing records topic, objective, included/excluded scope, ER01–ER05, terminology, source/date/independence limits and `model_scope = demand_side_and_system_interconnect`.

The hierarchical question tree covers drivers, architecture, key technology, components/materials, manufacturing/yield, routes, bottlenecks, value change, counterarguments and validation. Every question has ID, parent, why it matters, related ERs, status and gap reference.

The grounded model may represent:

```text
AI workload
→ compute system
→ server / rack / cluster
→ scale-up / scale-out interconnect
→ accelerator / switch / NIC / DPU
→ copper or optical interconnect boundary
```

PCB materials, process, equipment, manufacturing and test appear only as unverified extensions linked to skeletons/gaps. The model is never called a complete AI PCB industry model.

## 8. Evidence locator

Formal locators contain:

```text
artifact_id
normalized_document_id
section_index
section_hash
heading
locator_note
content_span (optional)
```

Rules:

- section hash is mandatory and identifies the evidence;
- index aids reading but cannot identify evidence alone;
- heading is auxiliary;
- locator note cannot add facts or contribute to grounding;
- normalized documents must trace to immutable raw artifacts;
- hash mismatch invalidates the locator;
- optional spans do not require historical renormalization;
- snippets, candidate descriptions and acquisition metadata are not正文 evidence.

## 9. Evidence-chain governance

The inventory records acquired/blocked coverage, raw/normalized bindings, exact duplicates, suspected common origin, source family, reference-only role, date status and missing independent secondary coverage.

Exact duplicates count as one chain. Suspected common-origin groups count as one provisional chain. File format differences do not establish independence.

## 10. ER and atomic claim separation

```text
atomic claim sufficiency != ER sufficiency
```

Each ER assessment records assessed, sufficient, open, conflicted and missing claim IDs plus overall status, reason, governance requirements and unresolved requirements.

ER status is recomputed from atomic claims and ER independence, counter-search, freshness, scope and denominator requirements. A strong official product fact cannot make the whole ER sufficient.

## 11. Claim ledger and calculated grounding

Claims contain ID, text, type, scope, preconditions, ERs, evidence links, stance, independence, freshness, status, evidence strength, assessment confidence/reason, limitations, counterevidence and falsification conditions.

Enums:

- claim type: `fact`, `inference`, `hypothesis`, `judgment`;
- stance: `support`, `oppose`, `mixed`, `contextual`, `non_evidence`;
- status: `sufficient`, `insufficient`, `conflicted`, `open`, `not_assessable`;
- confidence: `very_low < low < medium < high`.

Grounding is calculated. A grounded claim requires valid normalized-section evidence, direct support, correct evidence-chain treatment, scope alignment, compatible freshness/confidence and no incompatible unresolved contradiction.

Contextual evidence may define background, scope, limits or alternatives. It cannot be sole direct support, improve confidence or contribute domain coverage.

Evidence strength and assessment confidence are separate.

## 12. Evidence-grounded mechanisms

Grounded mechanisms are physically separated. They contain problem, bounded principle, variables, constraints/tradeoffs, scope, alternatives, metrics, evidence, confidence and open questions.

Technical explanation is structured as:

```text
explanation_steps:
  - statement
  - supporting_claim_ids

key_variable_grounding:
  - variable
  - supporting_claim_ids
```

Every supporting claim must be grounded. Synthesis may combine claims but cannot exceed their common coverage or introduce an unregistered premise.

Mechanism confidence is capped by the lowest allowed level across claim strength, scope alignment, independence, freshness and contradiction status.

## 13. Unverified mechanism skeletons

Skeletons are physically separate and may contain research questions, candidate variables, hypothesized relationships, evidence types, source classes, search terms, gap IDs and statuses `unverified_hypothesis`, `open`, `insufficient` or `not_assessable`.

They cannot contain verified principles or participate in ER sufficiency, grounded mechanisms/edges, bottleneck/value judgments, coverage, capability or company readiness.

Expected skeleton areas include signal integrity, insertion loss, layer count, high-speed laminate, back drilling, lamination, alignment, thermal coupling, test and yield.

## 14. Causal graph

Grounded and hypothesized edges are physically separated.

A grounded edge requires grounded endpoints, a grounded mechanism, claim-backed explanation steps, at least one claim supporting the relationship itself, necessary conditions, alternatives, failure conditions, no critical unresolved contradiction and no hypothesized bridge.

Facts supporting A and B separately do not prove A causes B.

Hypothesized edges use `unverified_hypothesis`, link evidence gaps and contribute nothing to grounded coverage, bottleneck/value judgment or capability. Multiple hypothesized edges cannot compose into a grounded chain.

## 15. Route comparison

Route comparisons cover common problem, principle differences, performance, cost, power, distance, manufacturability, maturity, scope, substitution/coexistence, metrics, evidence tendency and open questions.

Current evidence may support bounded comparisons of scale-up/scale-out, Ethernet/InfiniBand roles and electrical/photonic boundaries. It must not force a unique winner.

## 16. Limited system bottleneck judgments

Only these domains are allowed:

- AI system architecture;
- accelerator interconnect;
- network fabric;
- DPU;
- optical boundary.

PCB materials, manufacturing, test, yield and effective capacity are prohibited from the grounded bottleneck array and remain gaps/hypotheses.

Every allowed judgment needs evidence, counterarguments, reason, confidence, verification metrics and invalidation conditions. Open/insufficient is valid; a confirmed bottleneck is not required.

## 17. Value-change hypotheses

Allowed statuses are only:

- `open`;
- `evidence_gap_linked`;
- `not_eligible_for_judgment`.

They contribute no coverage or readiness and cannot use company/investment semantics such as winner, profit, valuation or recommendation. System bandwidth growth cannot automatically imply PCB content, laminate value, manufacturing profit or capacity conclusions.

## 18. Contradictions and evidence gaps

Contradictions/uncertainty explicitly record differing definitions/denominators, ER05 unresolved denominator, exact duplicates, suspected common origin, unknown dates, vendor-marketing limits, missing independent secondary evidence, blocked evidence and unanswered questions.

Every `evidence_gap_referral` records domain, blocked question/claim, insufficiency reason, impacted objects/capability, required evidence types, preferred source classes, search terms, priority, stop condition and `automatic_acquisition_authorized = false`.

Model prior may propose questions, variables, source types and queries. It is never evidence or verified explanation.

## 19. Deterministic report

Title:

> **AI PCB 研究认知基线 v1：AI 系统互连需求侧证据与 PCB 技术缺口**

Renderer output is UTF-8, Unicode NFC, LF, one final newline, stable-ID ordered and contains no current time/random/environment-dependent content.

Validation regenerates the report and compares `canonical_render_hash`; byte comparison is an additional strict check.

Grounded, skeleton, gap and contradiction have explicit labels. Evidence displays compactly:

```text
[claim: CLM-001]
Evidence: ART-003 / DOC-003 / section 12 / hash abcdef...
```

Locator notes are visually distinct from source content.

## 20. Deterministic audit

Audit contains only bindings, rule versions, computed capability, metrics, violations/warnings, deterministic answers and supporting/blocking IDs. It cannot contain new cognition.

Persisted audit must equal the recomputed result.

Each of eight fixed audit questions contains `question_id`, computed answer, status, supporting IDs, blocking IDs and calculation rule:

1. What does the system understand?
2. What only has research structure?
3. Which key segments lack evidence?
4. Which causal relationships remain hypotheses?
5. Can PCB technical bottlenecks be judged?
6. Can material/manufacturing value migration be judged?
7. Could the report overstate completeness?
8. Which cognition breaks require evidence review first?

## 21. Domain matrix and capability rules

Domain states are:

- `evidence_grounded`;
- `unverified_skeleton_only`;
- `not_assessable`;
- `conflicted`.

Domains include system architecture, accelerator interconnect, network fabric, DPU, optical boundary, signal integrity, PCB materials, PCB manufacturing, PCB test, yield and effective capacity.

Expected current computed result:

```yaml
overall_capability: partial_industry_cognition_demand_side_only
ai_system_interconnect_cognition: evidence_grounded
signal_integrity_and_pcb_mechanism_cognition: unverified_skeleton_only
pcb_material_and_manufacturing_cognition: not_assessable
pcb_industry_bottleneck_judgment: not_available
full_ai_pcb_industry_cognition: not_achieved
company_mapping_readiness: false
next_required_action: evidence_gap_review
automatic_gap_acquisition_authorized: false
```

These are computed from the matrix, not hard-coded as AI PCB answers.

Fail-closed ceilings:

- missing grounded materials/manufacturing/test/yield prevents full cognition;
- skeleton-only key mechanisms prevent PCB bottleneck judgment;
- critical hypothesized edges prevent grounded value judgment;
- unreviewed gaps prevent company mapping;
- evidence-gap review never authorizes acquisition.

## 22. Validator pipeline

```text
load
→ schema validation
→ baseline binding validation
→ locator/raw/normalized hash validation
→ evidence-chain validation
→ claim grounding calculation
→ ER status calculation
→ mechanism and causal validation
→ judgment/scope validation
→ domain and capability computation
→ report regeneration/hash comparison
→ persisted audit recomputation/comparison
```

Fail closed on missing important-claim evidence, judgment without reason, ungrounded mechanism steps, causal edge without relationship evidence, excessive confidence, duplicate independence inflation, definite freshness from unknown dates, skeleton contamination, hypothesized-chain promotion, prohibited PCB bottleneck judgments, report-only conclusions, capability inflation, downstream role leakage or Stage A2/Stage B authorization.

Scope leakage is primarily checked through object type, role, target scope, assessment level and downstream-use fields. Keyword scanning is only a secondary warning because publisher names are legitimate evidence metadata.

## 23. Read-only CLI and exit codes

```text
research-project-v2-1 cognition validate
research-project-v2-1 cognition show
research-project-v2-1 cognition audit
research-project-v2-1 cognition render
```

- `validate`: verifies all structure, bindings, grounding, report, audit and scope;
- `audit`: validates first, then prints recomputed audit JSON;
- `render`: prints canonical Markdown;
- `show`: uses `audit projection + package summary` and fixed enums, with no separate interpretation logic.

Exit categories:

```text
0 = valid / computed
1 = validation failure
2 = input or binding missing
3 = upstream hash drift
4 = scope violation
```

No create/build/fix/refresh/acquire command is added. The committed artifacts are produced once through the controlled implementation process.

## 24. Expected research boundary

Existing evidence may ground accelerator-system composition, NVLink/NVSwitch or integrated networking roles, internal/external network separation, NIC/DPU roles, switch throughput/radix, rack fabrics and optical interconnect as a vendor-stated boundary route.

It cannot verify insertion-loss mechanisms, layer-count drivers, laminate mechanisms, back drilling, lamination/alignment, PCB test/yield, effective capacity, PCB manufacturing bottlenecks or material/manufacturing value migration. Those become skeletons and gaps.

## 25. Test and acceptance strategy

Focused tests cover discriminators, baseline immutability, locator/hash drift, raw-normalized traceability, duplicate/common-origin handling, unknown-date freshness, calculated grounding, contextual misuse, confidence ceilings, skeleton contamination, causal relationship evidence, hypothesized-chain promotion, prohibited bottlenecks/value states, capability ceilings, canonical report/audit, read-only CLI and exit codes, downstream role leakage and exact attribution.

Required V2/R1-R2 and V1/Theme/Dashboard regressions remain offline.

Completion requires one valid package, one deterministic report, one recomputable audit, ER01–ER05 assessment, grounded demand-side model/edges, separated skeletons/gaps, preserved uncertainties, no downstream leakage, parseable JSON/JSONL, exact allowlist and a clean worktree.

The stage stops after reporting. It does not acquire gap evidence or proceed to company mapping.
