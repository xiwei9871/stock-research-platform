# AI PCB Stage A Scope Correction Design

## 1. Purpose

This change reclassifies the completed AI Compute PCB Stage A acquisition from an equity-candidate activity to a global-industry-reference activity for an A-share-focused investment platform.

The correction is append-only. It preserves every acquisition fact and adds a machine-enforceable governance overlay that controls how the existing artifacts may be interpreted and what downstream work is authorized.

## 2. Immutable baseline

The following baseline remains unchanged:

- D0 commit: `1535f6d`;
- Stage A commit: `ae4e70e`;
- checkpoint path: `artifacts/research_projects/v2_1/acquisition/checkpoints/acquisition_checkpoint:a5f7627d8726c9405ba67a75.json`;
- checkpoint ID: `acquisition_checkpoint:a5f7627d8726c9405ba67a75`;
- embedded canonical content hash: `a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e`;
- current checkpoint file-byte SHA-256: `e2b91137df1c01a7fa7b30c8ed9cdd8b052e30ad3a57a274519fab20cb2f07ae`.

The embedded canonical content hash and file-byte SHA-256 are different measurements. The governance artifact records both with explicit field names. The user-supplied checkpoint hash remains the authoritative canonical content hash; the byte hash provides an additional repository-integrity check.

No candidate, attempt, raw artifact, normalized representation, acquisition history, provenance record, blocked result, failure result, date status, or checkpoint field is rewritten.

## 3. Chosen architecture

Create a standalone Schema 2.4.0 governance artifact rather than extending or superseding the acquisition checkpoint.

The new layer has three responsibilities:

1. declare the corrected investment and entity scope;
2. restrict permitted assessment and downstream transitions;
3. define Stage A2 as a research-only plan without executing it.

Acquisition Schema 2.3.0 continues to describe what was acquired. Governance Schema 2.4.0 describes how those immutable facts may be used.

Rejected alternatives:

- A superseding acquisition checkpoint would mix acquisition state with governance decisions.
- Documentation-only correction would not prevent scope drift or downstream misuse.

## 4. Artifact layout

Add:

```text
artifacts/research_projects/v2_1/
├── governance/
│   └── stage_a_scope_correction_v1.json
└── schema/
    └── stage_a_scope_correction_v2_4.schema.json
```

The governance artifact is canonical JSON and contains its own `content_hash`, calculated with the existing canonical hashing rules while excluding the `content_hash` field itself.

The artifact is immutable after creation. Any future correction must be a new decision artifact referencing this decision rather than editing it.

## 5. Scope correction model

The artifact must declare:

- `decision_type = stage_a_scope_correction`;
- `investment_market_scope = A_share`;
- `original_stage = stage_a_acquisition`;
- the original checkpoint ID, canonical content hash, and file-byte SHA-256;
- `corrected_stage_role = global_industry_reference_acquisition`;
- `corrected_status = global_industry_reference_acquisition_complete`;
- `global_entities_role = industry_reference_only`;
- `global_equity_assessment_allowed = false`;
- `a_share_candidate_coverage_claimed = false`;
- `evidence_assessment_allowed = industry_claim_level_only`;
- `company_level_assessment_allowed = false`;
- `stage_b_authorized = false`;
- `next_stage = stage_a2_a_share_supply_chain_mapping`.

It also records provenance, decision rationale, evidence-use rules, preserved acquisition rules, entity classifications, and the Stage A2 plan.

## 6. Entity classification overlay

The artifact classifies these entities:

- NVIDIA;
- Intel / Habana;
- Cisco;
- Broadcom;
- Lightmatter;
- Supermicro.

Every entity receives:

```text
entity_role = global_industry_reference
investment_candidate = false
eligible_for_a_share_review_universe = false
eligible_for_company_scoring = false
eligible_for_signal = false
eligible_for_admission = false
```

Lightmatter Passage may remain an ER04 boundary or alternative-technology reference, but the overlay cannot assign an equity conclusion.

The validator rejects any listed entity if it is marked as an investment candidate, A-share candidate, company-scoring target, signal target, or admission target.

## 7. Evidence-use boundary

The existing ER01–ER05 definitions remain unchanged.

Existing global primary artifacts may later support industry-level assessment of:

- architecture and technology routes;
- product specifications and capability boundaries;
- component and process requirements;
- value-chain segment identification;
- upstream demand mechanisms;
- technology substitution risk;
- industry claims used as inputs to A-share mapping.

They may not directly support A-share company exposure, qualification, capacity, orders, revenue, profit, beneficiary ranking, or investment value.

The governance artifact encodes these invariants:

```text
global_reference_coverage != a_share_candidate_coverage
primary_source_count != evidence_sufficiency
industry_claim_support != company_exposure_support
```

Company-level evidence must later come from company-specific and independently auditable material.

## 8. Preserved acquisition rules

The correction restates, without changing, the existing rules:

- blocked candidates count toward attempt coverage only;
- exact duplicates count as one evidence chain during assessment;
- suspected common-origin sources default to one provisional chain;
- unknown publication dates remain unknown and retain freshness warnings;
- ER05 denominator reconciliation remains open;
- Widen remains fail-closed with no security exception;
- network acquisition remains explicit direct HTTP with provider-local `trust_env=False`.

## 9. Stage A2 plan

The artifact defines `Stage A2 — A-share Supply-chain Mapping` with `plan_status = planned` and `research_only = true`.

Its required object flow is:

```text
global_technology_claim
    -> component_or_process_requirement
    -> value_chain_segment
    -> a_share_candidate_hypothesis
    -> company_specific_evidence_requirement
```

The plan may define candidate mapping dimensions, including high-speed PCB, high-layer-count PCB, HDI, high-speed CCL and resin, connectors, copper cables, optical modules and components, switches, servers and racks, power, liquid cooling, advanced packaging, testing and manufacturing equipment, and domestic interconnect chips.

These dimensions are hypotheses for future traceable mapping, not confirmed beneficiaries. The plan does not contain company names, company scores, stock recommendations, signals, admissions, portfolios, strategies, or acquisition attempts.

Stage A2 acceptance criteria require traceability from an industry claim through a component or process requirement to a value-chain segment before an A-share candidate hypothesis can be created. `NVIDIA demand growth -> A-share company necessarily benefits` is explicitly invalid.

## 10. Validation boundary

Add a focused governance loader and validator with no database, API, dashboard, or CLI dependency.

Validation has two layers:

1. JSON Schema validates the standalone shape, enums, required fields, booleans, entity records, provenance, and Stage A2 plan structure.
2. Semantic validation verifies the original checkpoint exists, its ID and embedded canonical hash match, its current file-byte SHA-256 matches the governance record, every required global entity has the restrictive classification, forbidden downstream concepts are absent, and the artifact content hash is valid.

The validator fails closed if the original checkpoint drifts or if governance flags allow company-level or downstream use.

## 11. Tests and TDD sequence

Tests are written and observed failing before implementation.

Focused tests cover:

- valid scope correction schema and semantic validation;
- exact original checkpoint ID and canonical hash binding;
- file-byte SHA-256 drift detection;
- rejection of each forbidden entity role or eligibility flag;
- rejection of global coverage being claimed as A-share candidate coverage;
- rejection of global equity or company-level assessment;
- rejection of Stage B authorization;
- requirement that next stage is Stage A2;
- Stage A2 `research_only` and `planned` state;
- rejection of signal, admission, score, portfolio, strategy, recommendation, or executed acquisition content;
- canonical content-hash verification;
- original checkpoint bytes and embedded hash remaining unchanged;
- exact allowlist attribution.

After focused tests, run the existing acquisition suite, V2/R1-R2 compatibility suite, V1/Theme/Dashboard regression, JSON/JSONL parsing, sensitive-data scan, and clean-worktree verification.

## 12. Documentation and scope attribution

Append a `Scope Correction` section to `docs/research_operating_layer_v2_r2b_ai_pcb_stage_a_acquisition.md`; do not rewrite its historical acquisition report.

Add `docs/research_operating_layer_v2_r2b_ai_pcb_scope_correction_and_stage_a2_plan.md` for the full governance decision and Stage A2 plan.

Add a machine-readable exact allowlist based on commit `ae4e70e`. It permits only the new governance schema/artifact, focused validator and tests, documentation, and scope-guard updates. It forbids acquisition history, research versions, V1, other pilots, dashboard, API, database, company scoring, stock scoring, watchlist, strategy, signal, admission, and portfolio paths.

## 13. Non-goals

This change does not:

- rerun acquisition;
- create Evidence Assessment;
- change ER01–ER05;
- create A-share candidates;
- begin company research;
- authorize Stage B;
- generate `v0.2.2` or `v0.3.0`;
- modify V1, other pilots, Dashboard, API, database, or trading workflows.

## 14. Completion condition

Completion requires a new committed governance artifact and validator, unchanged original checkpoint bytes and canonical hash, all required tests and regressions passing, all JSON/JSONL parseable, exact path attribution, no scope leakage, and a clean worktree.

Execution stops after the scope correction and Stage A2 plan are committed and verified.
