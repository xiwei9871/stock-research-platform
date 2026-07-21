# Stage A Industry Cognition and Evidence Synthesis Baseline v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute a deterministic, evidence-grounded AI PCB cognition baseline that proves bounded AI-system-interconnect understanding while preserving PCB material/manufacturing mechanisms as skeletons and evidence gaps.

**Architecture:** A standalone Schema 2.5.0 validates one integrated cognition package and one deterministic audit. Focused modules load immutable evidence, calculate claim/mechanism/causal grounding, render canonical Markdown, and recompute capability/audit output. The existing CLI exposes only read-only validate/show/audit/render commands.

**Tech Stack:** Python 3, JSON Schema Draft 2020-12, RFC 8785 canonical JSON, SHA-256, pytest, argparse, deterministic Markdown rendering.

---

## File map

- Create `artifacts/research_projects/v2_1/schema/industry_cognition_baseline_v2_5.schema.json`: package/audit discriminator and structural constraints.
- Create `src/stock_research/research_project_v2_1/cognition.py`: canonical loader, upstream/locator validation, grounding, ER calculation and scope rules.
- Create `src/stock_research/research_project_v2_1/cognition_render.py`: canonical deterministic Markdown renderer.
- Create `src/stock_research/research_project_v2_1/cognition_audit.py`: domain matrix, capability computation and eight deterministic audit answers.
- Modify `src/stock_research/research_project_v2_1/layout.py`: analysis/report paths.
- Modify `src/stock_research/research_project_v2_1/schema.py`: Schema 2.5.0 registry.
- Modify `src/stock_research/research_project_v2_1/cli.py`: read-only cognition command group.
- Create `tests/test_research_project_v2_1_cognition.py`: package, grounding, report and audit tests.
- Create `tests/test_research_project_v2_1_cognition_cli.py`: CLI and exit-code tests.
- Create `artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_package_v1.json`: integrated cognition source of truth.
- Create `artifacts/research_projects/v2_1/reports/ai_pcb_industry_cognition_report_v1.md`: canonical package projection.
- Create `artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_audit_v1.json`: deterministic audit snapshot.
- Create `docs/research_operating_layer_v2_stage_a_industry_cognition_method.md`: concise method and boundary document.
- Create `artifacts/research_projects/v2_1/analysis/ai_pcb_cognition_exact_allowlist.json`: exact attribution.
- Modify `tests/test_research_project_v2_1_r2b_scope_guard.py`: new immutable-baseline and allowlist range.
- Modify `tests/test_research_project_v2_1_schema.py`: public schema inventory.

### Task 1: Define the package/audit schema contract

**Files:**
- Create: `tests/test_research_project_v2_1_cognition.py`
- Create: `artifacts/research_projects/v2_1/schema/industry_cognition_baseline_v2_5.schema.json`
- Modify: `src/stock_research/research_project_v2_1/schema.py`
- Modify: `tests/test_research_project_v2_1_schema.py`

- [ ] **Step 1: Write a failing package discriminator test**

Create a minimal valid package fixture with all required arrays present and capability fields absent:

```python
def minimal_package() -> dict:
    return {
        "schema_version": "2.5.0",
        "artifact_type": "industry_cognition_package",
        "package_id": "industry_cognition_package:ai_pcb:v1",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "renderer_version": "industry_cognition_markdown_v1",
        "baseline_bindings": {},
        "research_framing": {},
        "research_question_tree": [],
        "evidence_inventory": {},
        "er_assessments": [],
        "claim_assessment_ledger": [],
        "grounded_system_model": {"nodes": [], "edges": []},
        "unverified_system_extensions": [],
        "evidence_grounded_mechanisms": [],
        "unverified_mechanism_skeletons": [],
        "grounded_causal_edges": [],
        "hypothesized_causal_edges": [],
        "technology_route_comparisons": [],
        "limited_system_bottleneck_judgments": [],
        "value_change_hypotheses": [],
        "contradictions_and_uncertainties": [],
        "evidence_gap_referrals": [],
        "verification_and_falsification": [],
        "provenance": PROVENANCE,
        "content_hash": "0" * 64,
    }


def test_schema_v2_5_accepts_package_and_rejects_capability_fields() -> None:
    package = minimal_package()
    validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", package)
    package["overall_capability"] = "complete"
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", package)
```

- [ ] **Step 2: Write a failing audit discriminator test**

```python
def minimal_audit() -> dict:
    return {
        "schema_version": "2.5.0",
        "artifact_type": "industry_cognition_audit",
        "audit_id": "industry_cognition_audit:ai_pcb:v1",
        "package_id": "industry_cognition_package:ai_pcb:v1",
        "package_content_hash": "a" * 64,
        "report_content_hash": "b" * 64,
        "renderer_version": "industry_cognition_markdown_v1",
        "capability_rule_version": "industry_cognition_capability_v1",
        "domain_matrix_version": "industry_cognition_domains_v1",
        "audit_question_set_version": "industry_cognition_audit_questions_v1",
        "domain_coverage": [],
        "computed_capability": {},
        "coverage_metrics": {},
        "audit_answers": [],
        "violations": [],
        "warnings": [],
        "content_hash": "0" * 64,
    }


def test_schema_v2_5_accepts_audit_and_rejects_cognition_objects() -> None:
    audit = minimal_audit()
    validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", audit)
    audit["claim_assessment_ledger"] = []
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", audit)
```

- [ ] **Step 3: Run RED**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py
```

Expected: `RESEARCH_PROJECT_V2_1_SCHEMA_NOT_FOUND`.

- [ ] **Step 4: Implement the schema and registry**

Register:

```python
"industry_cognition_baseline_v2_5": "industry_cognition_baseline_v2_5.schema.json",
```

The schema must use `oneOf` keyed by `artifact_type`, `additionalProperties: false`, fixed enums, lowercase SHA-256 patterns and the common provenance definition. Package and audit required fields are exactly those in the approved design.

- [ ] **Step 5: Update the public schema inventory and run GREEN**

Add the schema filename and registry entry to `tests/test_research_project_v2_1_schema.py`, increase the exact schema count by one, then run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py tests/test_research_project_v2_1_schema.py
```

Expected: zero failures.

- [ ] **Step 6: Commit**

```bash
rtk git add artifacts/research_projects/v2_1/schema/industry_cognition_baseline_v2_5.schema.json src/stock_research/research_project_v2_1/schema.py tests/test_research_project_v2_1_cognition.py tests/test_research_project_v2_1_schema.py
rtk git commit -m "feat: define industry cognition baseline schema"
```

### Task 2: Implement immutable loading and evidence locators

**Files:**
- Create: `src/stock_research/research_project_v2_1/cognition.py`
- Modify: `src/stock_research/research_project_v2_1/layout.py`
- Modify: `tests/test_research_project_v2_1_cognition.py`

- [ ] **Step 1: Write failing binding tests**

Add tests named `test_validate_package_rejects_checkpoint_or_scope_hash_drift`, `test_validate_locator_requires_raw_normalized_traceability` and `test_validate_locator_rejects_section_hash_drift`. Each test copies the real bound artifact into a temporary layout, mutates exactly one hash or binding, calls the public validator and asserts the precise cognition error code and failing field.

Use copied real repository artifacts in a temporary `LayeredResearchLayout`; do not mock hashes.

- [ ] **Step 2: Run RED**

Expected: import failure for `research_project_v2_1.cognition`.

- [ ] **Step 3: Implement loader and binding APIs**

Implement public functions `load_cognition_package(path, layout=None)`, `validate_baseline_bindings(package, layout)` and `validate_evidence_locator(locator, layout)`, plus `CONFIDENCE_ORDER = {"very_low": 0, "low": 1, "medium": 2, "high": 3}`.

`validate_evidence_locator` must read the canonical normalized document, verify its raw artifact binding, select the section by index, require the exact section hash and ignore heading/locator note for identity.

Add layout properties:

```python
@property
def analysis_dir(self) -> Path:
    return self.root / "analysis"

@property
def reports_dir(self) -> Path:
    return self.root / "reports"
```

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py
rtk git add src/stock_research/research_project_v2_1/cognition.py src/stock_research/research_project_v2_1/layout.py tests/test_research_project_v2_1_cognition.py
rtk git commit -m "feat: validate cognition evidence bindings"
```

### Task 3: Calculate claim grounding and ER status

**Files:**
- Modify: `src/stock_research/research_project_v2_1/cognition.py`
- Modify: `tests/test_research_project_v2_1_cognition.py`

- [ ] **Step 1: Write failing grounding tests**

Cover:

- direct support plus valid locator can ground a scoped fact;
- contextual-only evidence cannot ground a claim;
- exact duplicate cannot count as a second independent chain;
- suspected common-origin counts as one provisional chain;
- unknown-date evidence cannot have `freshness_status=confirmed_current`;
- `grounding_status` must equal recomputed status;
- high confidence fails when freshness/independence/contradiction ceiling is lower.

Add tests named `test_calculate_claim_grounding_uses_direct_support_and_chain_count`, `test_contextual_only_evidence_does_not_ground_claim`, `test_unknown_date_cannot_receive_definite_freshness` and `test_claim_confidence_cannot_exceed_calculated_ceiling`. Use explicit fixture claims and assert the returned grounded state, chain count, blockers and ceiling.

- [ ] **Step 2: Run RED**

Expected: missing `calculate_claim_grounding`.

- [ ] **Step 3: Implement calculation**

Implement `calculate_claim_grounding(claim, inventory, valid_locators)` and `calculate_er_assessment(er, claims_by_id)` as pure functions.

Return fixed `grounded/not_grounded` state, evidence-chain count, confidence ceiling and blockers. ER calculation must compare assessed/sufficient/open/conflicted/missing IDs with recomputed claim status and governance requirements.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py
rtk git add src/stock_research/research_project_v2_1/cognition.py tests/test_research_project_v2_1_cognition.py
rtk git commit -m "feat: calculate cognition claim and er grounding"
```

### Task 4: Enforce mechanism, causal, bottleneck and value boundaries

**Files:**
- Modify: `src/stock_research/research_project_v2_1/cognition.py`
- Modify: `tests/test_research_project_v2_1_cognition.py`

- [ ] **Step 1: Write failing semantic tests**

Add six tests with the names above. Each test mutates one otherwise-valid package and asserts the exact semantic violation: skeleton contamination, confidence overflow, missing relationship claim, hypothesized bridge, prohibited PCB bottleneck domain, or prohibited value status.

- [ ] **Step 2: Run RED**

Expected: missing semantic validation functions.

- [ ] **Step 3: Implement semantic validators**

Implement `validate_grounded_mechanisms(package, claims_by_id)`, `validate_causal_edges(package, claims_by_id)` and `validate_judgment_boundaries(package)`. Define the allowed bottleneck domains and value statuses exactly as listed in the approved design.

Every explanation step and variable map must reference grounded claims. Every grounded edge requires a claim with `claim_scope=relationship`. Skeleton and hypothesized IDs are forbidden from grounded arrays.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py
rtk git add src/stock_research/research_project_v2_1/cognition.py tests/test_research_project_v2_1_cognition.py
rtk git commit -m "feat: enforce cognition reasoning boundaries"
```

### Task 5: Implement deterministic capability and audit computation

**Files:**
- Create: `src/stock_research/research_project_v2_1/cognition_audit.py`
- Modify: `tests/test_research_project_v2_1_cognition.py`

- [ ] **Step 1: Write failing domain/capability tests**

Add five tests with the names above. Assert the exact four domain states, zero contribution from skeletons, the approved capability ceiling, canonical audit equality and eight versioned audit answers with supporting/blocking IDs.

- [ ] **Step 2: Run RED**

Expected: import failure for `cognition_audit`.

- [ ] **Step 3: Implement fixed rules**

Define the three version constants exactly as shown, then implement pure functions `compute_domain_coverage(package)`, `compute_capability(package, coverage)`, `compute_audit(package, report_bytes)` and `validate_persisted_audit(audit, expected)`.

The algorithm must produce the approved capability values from the current expected coverage without checking project name or hard-coding AI PCB as a special case.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py
rtk git add src/stock_research/research_project_v2_1/cognition_audit.py tests/test_research_project_v2_1_cognition.py
rtk git commit -m "feat: compute industry cognition capability audit"
```

### Task 6: Implement canonical report rendering

**Files:**
- Create: `src/stock_research/research_project_v2_1/cognition_render.py`
- Modify: `tests/test_research_project_v2_1_cognition.py`

- [ ] **Step 1: Write failing renderer tests**

Cover stable sorting, NFC, LF, one final newline, fixed title, no runtime fields, explicit grounded/skeleton/gap/contradiction labels and compact evidence locator display.

Add tests named `test_render_report_is_canonical_and_order_independent`, `test_render_report_contains_only_package_objects` and `test_validate_report_rejects_added_claim_or_hash_drift`, using two packages with reversed non-semantic array order and a report with one injected claim line.

- [ ] **Step 2: Run RED**

Expected: import failure for `cognition_render`.

- [ ] **Step 3: Implement renderer**

Define the renderer version and report title exactly as shown, then implement `render_cognition_report(package)`, `canonical_render_hash(package)` and `validate_persisted_report(package, report_bytes)`.

Build every report section from sorted package objects. Do not add explanatory prose not stored in a structured package field.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py
rtk git add src/stock_research/research_project_v2_1/cognition_render.py tests/test_research_project_v2_1_cognition.py
rtk git commit -m "feat: render deterministic cognition report"
```

### Task 7: Add the strictly read-only CLI

**Files:**
- Modify: `src/stock_research/research_project_v2_1/cli.py`
- Create: `tests/test_research_project_v2_1_cognition_cli.py`

- [ ] **Step 1: Write failing parser and output tests**

Add five CLI tests with the names above. Capture stdout and the repository tree before/after each command, assert no changed files, and assert the stable exit category for each injected error.

- [ ] **Step 2: Run RED**

Expected: argparse rejects `cognition`.

- [ ] **Step 3: Add parser and dispatch**

```python
cognition = commands.add_parser("cognition")
cognition_commands = cognition.add_subparsers(dest="cognition_command", required=True)
for name in ("validate", "show", "audit", "render"):
    command = cognition_commands.add_parser(name)
    command.add_argument("--package", required=True)
    command.add_argument("--report", required=True)
    command.add_argument("--audit", required=True)
```

`validate` returns JSON. `show` returns audit projection plus package counts. `audit` returns recomputed audit. `render` prints Markdown without JSON wrapping. No command writes files.

Map cognition domain errors to stable exit categories 1–4 without changing existing command exit behavior.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition_cli.py tests/test_research_project_v2_1_cli.py
rtk git add src/stock_research/research_project_v2_1/cli.py tests/test_research_project_v2_1_cognition_cli.py
rtk git commit -m "feat: add read only cognition cli"
```

### Task 8: Curate the AI PCB cognition package from existing evidence

**Files:**
- Create: `artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_package_v1.json`
- Modify: `tests/test_research_project_v2_1_cognition.py`

- [ ] **Step 1: Add a failing repository-package validation test**

```python
def test_repository_ai_pcb_cognition_package_is_valid_and_strictly_bounded() -> None:
    package = load_cognition_package(PACKAGE_PATH)
    result = validate_cognition_package(package)
    assert result["scope_leakage"] == []
    assert len(package["er_assessments"]) == 5
    assert package["research_framing"]["model_scope"] == "demand_side_and_system_interconnect"
```

- [ ] **Step 2: Run RED**

Expected: package file missing.

- [ ] **Step 3: Curate evidence-grounded claims**

Create claims for these evidence-covered subjects, each with real section hashes and locators:

- Gaudi compute/memory/network subsystem architecture;
- Gaudi integrated RoCE/NIC communication role;
- DGX H100/H200 GPU, NVSwitch/NVLink and external-network configuration;
- DGX B200 GPU/NVSwitch/NVLink and external-network configuration;
- SuperPOD separation of compute, storage and management fabrics;
- Cisco general-purpose rack-server PCIe/network configuration as bounded comparison context;
- Broadcom 51.2-Tbps switch-chip vendor specification;
- BlueField/DPU network-host interface and infrastructure role;
- Lightmatter Passage photonic data-rate/boundary claims, explicitly vendor-primary and not automatically support/oppose.

Use `fact` only for direct product/document statements. Cross-document conclusions use `inference` with lower confidence. All evidence dates remain unknown for freshness calculation even where正文 contains a date not promoted into acquisition metadata.

- [ ] **Step 4: Create ER01–ER05 assessments**

Expected overall states:

```text
ER01 = insufficient
ER02 = insufficient
ER03 = insufficient
ER04 = insufficient
ER05 = open, resolution_code = denominator_unresolved
```

Reasons must cite missing independent secondary evidence, incomplete counter-search, common-origin/duplicate constraints, unknown dates, blocked Supermicro evidence and ER05 denominator mismatch as applicable.

- [ ] **Step 5: Create system model, grounded mechanisms and edges**

Grounded mechanism subjects:

- accelerator-system internal versus external interconnect roles;
- NVLink/NVSwitch accelerator scale-up topology;
- integrated RoCE-based accelerator communication;
- external NIC/DPU network-host boundary;
- network-fabric/switch throughput and radix as system parameters.

Grounded causal edges stop at system-interconnect architecture. Each edge uses a relationship claim, necessary conditions, alternatives and failure conditions.

- [ ] **Step 6: Create skeletons and gap referrals**

Create separate skeleton/gap pairs for:

- signal integrity;
- insertion loss;
- PCB layer-count drivers;
- high-speed laminate/resin;
- back drilling;
- lamination and alignment;
- thermal interaction;
- PCB test;
- yield;
- effective capacity.

Every skeleton is `unverified_hypothesis`, has no supporting evidence locator, cannot feed grounded objects, and lists required source classes such as standards, peer-reviewed signal-integrity papers, laminate data sheets with test methods, PCB process engineering references, equipment specifications, reliability/test standards and independent manufacturing data.

- [ ] **Step 7: Add routes, limited judgments, value hypotheses and uncertainty**

Route comparisons:

- scale-up versus scale-out as complementary scopes;
- Ethernet versus InfiniBand roles with unresolved comparison limits;
- electrical versus photonic interconnect boundary with vendor-primary limitations.

Limited bottleneck judgments remain open/insufficient and only address accelerator communication or network fabric. Add no PCB-domain bottleneck judgment.

All value-change hypotheses are `evidence_gap_linked` or `not_eligible_for_judgment`.

Explicitly record exact duplicates, suspected common origin, unknown dates, vendor-marketing limits, missing secondary sources, blocked candidates and ER05 denominator uncertainty.

- [ ] **Step 8: Canonicalize, hash, validate and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py
rtk git add artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_package_v1.json tests/test_research_project_v2_1_cognition.py
rtk git commit -m "data: add ai pcb cognition package baseline"
```

### Task 9: Persist deterministic report and audit

**Files:**
- Create: `artifacts/research_projects/v2_1/reports/ai_pcb_industry_cognition_report_v1.md`
- Create: `artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_audit_v1.json`
- Modify: `tests/test_research_project_v2_1_cognition.py`

- [ ] **Step 1: Write failing repository projection tests**

Add repository tests with the three names above. Compare report bytes to renderer bytes, audit canonical JSON to recomputed audit, and every approved bounded capability enum to the recomputed result.

- [ ] **Step 2: Run RED**

Expected: report and audit files missing.

- [ ] **Step 3: Produce the report through the renderer**

Persist exactly `render_cognition_report(package)`. Do not hand-add prose after rendering.

- [ ] **Step 4: Produce the audit through `compute_audit`**

Persist the canonical audit with a self-excluding content hash. Expected capability is the approved partial-demand-side result, computed from the package.

- [ ] **Step 5: Run GREEN and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py tests/test_research_project_v2_1_cognition_cli.py
rtk git add artifacts/research_projects/v2_1/reports/ai_pcb_industry_cognition_report_v1.md artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_audit_v1.json tests/test_research_project_v2_1_cognition.py
rtk git commit -m "data: add deterministic ai pcb cognition report and audit"
```

### Task 10: Document method and lock exact scope attribution

**Files:**
- Create: `docs/research_operating_layer_v2_stage_a_industry_cognition_method.md`
- Create: `artifacts/research_projects/v2_1/analysis/ai_pcb_cognition_exact_allowlist.json`
- Modify: `tests/test_research_project_v2_1_r2b_scope_guard.py`

- [ ] **Step 1: Write failing documentation and scope tests**

Require the method document to explain package/report/audit roles, strict evidence grounding, skeleton limits, domain capability calculation, no acquisition and no company mapping.

Require the allowlist baseline `7280ba71b1694f1ac5938d8be258b9803dfc285e`, exact current paths, no acquisition/evidence mutation paths and no downstream paths.

- [ ] **Step 2: Run RED**

Expected: method and allowlist missing.

- [ ] **Step 3: Add method and allowlist**

The allowlist includes the design/plan documents, Schema 2.5.0, three cognition modules, CLI wiring, focused tests, package/report/audit and method document. It forbids acquisition, evidence/raw, evidence/normalized, governance correction, project versions, V1, other pilots, Dashboard, API, database and downstream artifacts.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_r2b_scope_guard.py tests/test_research_project_v2_1_cognition.py tests/test_research_project_v2_1_cognition_cli.py
rtk git add docs/research_operating_layer_v2_stage_a_industry_cognition_method.md artifacts/research_projects/v2_1/analysis/ai_pcb_cognition_exact_allowlist.json tests/test_research_project_v2_1_r2b_scope_guard.py
rtk git commit -m "docs: lock industry cognition baseline scope"
```

### Task 11: Final research and engineering audit

**Files:**
- No new files unless a verified defect requires a tested correction.

- [ ] **Step 1: Verify immutable upstream files**

Compare against baseline commit and verify canonical/file hashes for:

- acquisition checkpoint;
- scope correction artifact;
- all raw artifacts;
- all normalized documents;
- attempts and provenance.

Expected: no diff and no deletion.

- [ ] **Step 2: Run focused tests**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2_1_cognition.py tests/test_research_project_v2_1_cognition_cli.py tests/test_research_project_v2_1_schema.py tests/test_research_project_v2_1_r2b_scope_guard.py
```

- [ ] **Step 3: Run V2/R1-R2 regression**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_research_project_v2*.py
```

- [ ] **Step 4: Run V1/Theme/Dashboard regression**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_dashboard_*.py tests/test_theme_*.py tests/test_technology_industry_catalog*.py tests/test_schema.py
```

- [ ] **Step 5: Validate JSON/JSONL, canonical hashes and report hash**

Parse all JSON/JSONL, validate package/audit with Schema 2.5.0, recalculate self-excluding hashes, regenerate the report and compare canonical and byte hashes.

- [ ] **Step 6: Run all four CLI commands**

Use the committed package/report/audit paths. Verify `validate`, `show`, `audit` and `render` return exit 0 and do not modify the worktree.

- [ ] **Step 7: Audit research substance**

Produce the final factual summary from package/audit counts:

- ER01–ER05 statuses;
- grounded mechanisms;
- skeletons;
- grounded and hypothesized edges;
- limited bottleneck judgments;
- claim status counts;
- gaps and source types needed;
- duplicate/common-origin/date handling;
- report/package consistency;
- whether cognition is full AI PCB or demand-side-only.

Do not use test counts as the answer to the cognition-quality question.

- [ ] **Step 8: Audit leakage, partial files and exact attribution**

```bash
rtk git diff --name-only 7280ba71b1694f1ac5938d8be258b9803dfc285e..HEAD
rtk git diff --diff-filter=D --name-only 7280ba71b1694f1ac5938d8be258b9803dfc285e..HEAD
rtk git diff --check 7280ba71b1694f1ac5938d8be258b9803dfc285e..HEAD
rtk find artifacts/research_projects/v2_1 -type f -name '*.part'
rtk find artifacts/research_projects/v2_1 -type f -name '*.tmp'
```

Expected: only exact-allowlisted paths, no deletions, no partial files and no whitespace errors.

- [ ] **Step 9: Confirm clean worktree and final commit**

```bash
rtk git status --short
rtk git rev-parse HEAD
```

Expected: clean status and one final SHA. Stop without Stage A2, Stage B or acquisition.
