# Research Operating Layer V2 R2B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate that the Research Operating Layer can build auditable industry models, test real bottleneck hypotheses, explain value migration, and decide whether a bottleneck may enter Company Solution Mapping without producing company or stock conclusions.

**Architecture:** Reuse the R2A immutable project, evidence, provenance, lineage, security and governance stack. Add only the R2B object families that cannot be represented faithfully by R2A, then execute two pilots serially: AI Compute PCB first, High-End Medical Device second. Evidence stays external and immutable until a reviewed project version incorporates it.

**Tech Stack:** Python 3.14, JSON Schema 2020-12, pytest, canonical JSON/SHA-256, append-only JSON/JSONL artifacts, existing `research_project_v2_1` CLI and managed-path primitives.

---

## 1. Phase Boundary

Phase 1 consists only of the audit and design documents dated 2026-07-20. No external acquisition, schema change, project version, evidence artifact, company mapping, API, Dashboard or database change is authorized.

Phase 2 requires explicit user approval of the decisions listed at the end of this plan.

## 2. Phase 1 Files

Create only:

- `docs/research_operating_layer_v2_r2b_capability_and_gap_audit.md`
- `docs/research_operating_layer_v2_r2b_schema_extension_proposal.md`
- `docs/research_operating_layer_v2_r2b_ai_compute_pcb_design.md`
- `docs/research_operating_layer_v2_r2b_high_end_medical_device_design.md`
- `docs/research_operating_layer_v2_r2b_bottleneck_readiness_gate.md`
- `docs/research_operating_layer_v2_r2b_plan.md`

Do not modify current artifacts or production code in Phase 1.

## 3. Phase 2 — Minimum R2B Profile And Evidence Acquisition

### Task 1: Freeze Baseline And Add R2B Scope Guard

**Files:**

- Create: `tests/test_research_project_v2_1_r2b_scope_guard.py`
- Modify: `docs/research_operating_layer_v2_r2b_plan.md` only if approved commit hashes need recording

- [ ] Write a failing scope test that derives changed paths from an explicit approved R2B commit set.
- [ ] Reject R1/V1, Dashboard, API, database/migration, company/stock artifacts and the two non-executed pilot project directories.
- [ ] Permit only approved R2B schema/package/tests/docs, the two selected pilot directories and necessary root CLI delegation.
- [ ] Verify the current R1, R2A and selected V1 baselines through commit attribution, not shared `base..HEAD` tree claims.
- [ ] Run `rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_research_project_v2_1_r2b_scope_guard.py -q`.
- [ ] Commit `test: establish r2b scope attribution`.

### Task 2: Add The Additive R2B Schema Profile

**Files:**

- Create: `artifacts/research_projects/v2_1/schema/definitions_v2_2.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/industry_research_version_v2_2.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/industry_evidence_assessment_v2_2.schema.json`
- Modify: `src/stock_research/research_project_v2_1/semantic.py`
- Modify: `tests/test_research_project_v2_1_schema.py`
- Modify: `tests/test_research_project_v2_1_loader.py`
- Create: `tests/test_research_project_v2_1_r2b_schema.py`

- [ ] Write failing tests proving old four R2A versions still validate byte-for-byte without R2B collections.
- [ ] Write failing tests for industry model nodes/edges, bottleneck hypotheses, value migration analyses and readiness reviews.
- [ ] Add isolated 2.2 definitions, Industry version and assessment schemas; keep every 2.1 schema unchanged.
- [ ] Dispatch loader validation by schema version and prove 2.1 artifacts still validate without migration.
- [ ] Extend industry target types, Router methods, evidence requirement fields and causal edge counter links.
- [ ] Add semantic ID uniqueness, target resolution, relation, status, provenance and Industry-only boundary checks.
- [ ] Reject company capture and stock evaluation values in every new object.
- [ ] Run schema, loader and semantic suites; expected zero failures.
- [ ] Commit `feat: add minimal r2b industry research profile`.

### Task 3: Add R2B Stable-ID Diff

**Files:**

- Create: `src/stock_research/research_project_v2_1/diff.py`
- Create: `tests/test_research_project_v2_1_diff.py`
- Modify: `src/stock_research/research_project_v2_1/__init__.py`

- [ ] Write failing tests for added, modified, status-changed, removed-from-current-scope, superseded and unchanged objects.
- [ ] Include questions, claims, requirements, assessments, industry model, bottlenecks, causal graph, value migration, metrics, invalidation and readiness review.
- [ ] Require same project, direct ancestry and immutable input versions.
- [ ] Keep inputs unchanged and output deterministic UTF-8 JSON.
- [ ] Run focused diff tests and R1 diff regression.
- [ ] Commit `feat: diff layered industry research versions`.

### Task 4: Create Detailed R2B Design Version For AI PCB

**Files:**

- Create: `artifacts/research_projects/v2_1/projects/ai_compute_pcb_industry_bottleneck/versions/v0.2.0.json`
- Append: `artifacts/research_projects/v2_1/projects/ai_compute_pcb_industry_bottleneck/version_manifest.jsonl`
- Modify via maintenance transaction: `project.json` pointer and rebuildable index
- Create/modify focused pilot fixtures and tests only as required

- [ ] Generate `v0.2.0 research_design` with parent `v0.1.0`.
- [ ] Use `schema_version=2.2.0` and keep `incorporated_event_ids=[]` because project research events are deferred.
- [ ] Preserve unchanged object IDs and immutable creation provenance.
- [ ] Add the approved question tree, industry model, eight proposed bottleneck hypotheses, evidence matrix and Search Plans.
- [ ] Keep evidence/assessment arrays empty, conclusion unavailable and investment not_assessed.
- [ ] Run Design Gate, semantic validation, reference audit and stable-ID diff.
- [ ] Confirm Humanoid Robot, Storage and Medical project bytes are unchanged.
- [ ] Commit `data: design ai compute pcb bottleneck research`.

### Task 5: Acquire And Assess AI PCB Evidence

**Files:**

- Add immutable artifacts only under `artifacts/research_projects/v2_1/evidence/`
- Do not modify project version during collection

- [ ] Execute one requirement at a time using its approved Search Plan.
- [ ] Prioritize primary technical/engineering/customer/capacity evidence before professional secondary sources.
- [ ] Store inaccessible-source outcomes in source-candidate/acquisition audit status; do not fabricate locators or invent research events.
- [ ] Normalize documents and create assessment only for exact target/locator.
- [ ] Build source relationships before counting independence.
- [ ] Complete counter-evidence search for every bottleneck.
- [ ] Stop after coverage conditions are met or the requirement stop condition triggers.
- [ ] Run audit and coverage report; no bottleneck status may become confirmed automatically.
- [ ] Commit evidence in small, requirement-attributed batches.

### Task 6: Repeat Design And Acquisition For Medical Device

Start only after AI PCB first-round coverage review is accepted.

**Files:**

- Create Medical `v0.2.0 research_design` and append its manifest through the same maintenance protocol
- Add Medical evidence artifacts under the shared evidence directories

- [ ] Add the approved lifecycle model, question tree, ten proposed bottlenecks and requirement/search plans.
- [ ] Require product class, indication, hospital scope and cohort in every quantitative assessment.
- [ ] Keep registration, tender, installation, active use and recurring revenue distinct.
- [ ] Run the same acquisition, independence, freshness, conflict and counter-evidence workflow.
- [ ] Confirm Robot and Storage pilots remain unchanged.
- [ ] Commit design and evidence in separate reviewed commits.

## 4. Phase 3 — Industry Model, Bottleneck Validation And Versions

### Task 7: Build Reviewed Causal And Value Migration Models

**Files:**

- Modify only through new immutable pilot versions and supporting evidence artifacts
- Add focused semantic/gate/diff tests where behavior is new

- [ ] Link each critical causal edge to supporting and counter claims, metrics and boundary conditions.
- [ ] Create value migration analysis by dimension; separate short-term price from structural content.
- [ ] Reconcile quantitative units and denominators.
- [ ] Set each bottleneck to provisionally_supported, contested or rejected before any readiness review.
- [ ] Keep confirmed_for_current_scope unavailable until the full Gate passes.

### Task 8: Implement Bottleneck Readiness Gate

**Files:**

- Create: `src/stock_research/research_project_v2_1/bottleneck_gate.py`
- Create: `tests/test_research_project_v2_1_bottleneck_gate.py`
- Modify: `src/stock_research/research_project_v2_1/cli.py`
- Modify: `src/stock_research/research_project_v2_1/gates.py` only for shared verified-storage helpers

- [ ] Write failing tests for all 19 criteria and six output states.
- [ ] Require stored identity/version/lineage/evidence; no unverified public pass path.
- [ ] Return criteria results, failures, warnings, questions, gaps and actions; never a total score.
- [ ] Make stale, conflict, independence and effective-capacity failures deterministic.
- [ ] Add `gate --gate bottleneck-readiness --bottleneck ID`.
- [ ] Keep company/stock output checks blocking.
- [ ] Commit `feat: evaluate bottleneck readiness`.

### Task 9: Publish Review Candidate Versions

- [ ] Create AI PCB `v0.3.0 review_candidate` from `v0.2.0`.
- [ ] Create Medical `v0.3.0 review_candidate` only after its evidence review.
- [ ] Keep `incorporated_event_ids=[]` unless a separately approved event stream has been implemented; record all evidence/assessment references directly.
- [ ] Calculate canonical hash and append immutable manifest rows.
- [ ] Generate stable-ID diff for v0.1→v0.2 and v0.2→v0.3.
- [ ] Run Bottleneck Readiness Gate per bottleneck.
- [ ] Do not create any company mapping even when a bottleneck is ready.

## 5. Phase 4 — Independent Audit And Closure

- [ ] Run independent specification review.
- [ ] Run independent code/data quality review.
- [ ] Verify scope attribution by approved commits and exact paths.
- [ ] Run R2B, R2A, R1 and selected V1 regression suites.
- [ ] Parse every new JSON/JSONL and audit all hashes, manifests, IDs and locators.
- [ ] Scan for company rating, stock rating, price, valuation, recommendation, watchlist and strategy output.
- [ ] Verify Robot, Storage, 27 V1 themes, API, Dashboard and database paths are unchanged by R2B commits.
- [ ] Write R2B operator documentation and handoff; do not mark R3 complete.

## 6. Planned File Scope

Potential implementation scope after approval:

```text
artifacts/research_projects/v2_1/schema/**
artifacts/research_projects/v2_1/projects/ai_compute_pcb_industry_bottleneck/**
artifacts/research_projects/v2_1/projects/high_end_medical_device_industry_bottleneck/**
artifacts/research_projects/v2_1/evidence/**
artifacts/research_projects/v2_1/index/**
src/stock_research/research_project_v2_1/**
tests/test_research_project_v2_1_r2b_*.py
tests/test_research_project_v2_1_diff.py
tests/test_research_project_v2_1_bottleneck_gate.py
docs/research_operating_layer_v2_r2b_*.md
src/stock_research/cli.py only if root delegation must expose an approved subcommand
```

## 7. Explicitly Forbidden File Scope

```text
artifacts/research_projects/v2/**
artifacts/theme_decomposition/**
artifacts/technology_industry_catalog/**
the Humanoid Robot and New Energy Storage v2_1 project directories
dashboard/**
src/stock_research/dashboard/**
API route files
database schema or migration files
company/stock/watchlist/strategy artifacts
```

## 8. Risks And Stop Conditions

- Closed architecture data may prevent a reliable PCB BOM bridge.
- Medical utilization data may be unavailable at cohort level.
- Evidence may be dominated by vendor marketing or repeated secondary sources.
- Product generations, material grades or device categories may be non-comparable.
- Adding too many schema objects can recreate a large Theme JSON; reject fields without a Gate or audit use.
- If a Pilot cannot meet its primary/engineering evidence requirement, stop rather than lower the Gate.
- If new work requires company-level product/order/revenue research, stop at the R2B boundary and request R3 authority.

## 9. Decisions Required Before Phase 2

1. Approve the minimum R2B schema profile, including industry model, bottleneck, value migration and readiness review.
2. Approve deferring the project-level research update event stream and leaving incorporated event IDs empty.
3. Approve `v0.2.0 research_design` followed by `v0.3.0 review_candidate`.
4. Approve serial execution: AI PCB first, Medical second.
5. Approve the Pilot boundaries and hypothesis registers in the two design documents.
6. Approve adding only `diff` and `bottleneck-readiness` as necessary CLI capabilities.

No Phase 2 task starts until these decisions are confirmed.
