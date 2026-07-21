# AI PCB Stage A Scope Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an append-only, machine-enforceable governance correction that classifies Stage A as global industry reference acquisition for an A-share-only investment scope and defines, but does not execute, Stage A2.

**Architecture:** Add a standalone Schema 2.4.0 governance artifact and a focused semantic validator. The validator binds the decision to the immutable Stage A checkpoint using both its embedded canonical content hash and its file-byte SHA-256, rejects all global-entity investment eligibility, and enforces a research-only Stage A2 plan. Existing acquisition artifacts and schemas remain untouched.

**Tech Stack:** Python 3, JSON Schema Draft 2020-12, RFC 8785 canonical JSON, SHA-256, pytest, Git scope guards.

---

## File structure

- Create `artifacts/research_projects/v2_1/schema/stage_a_scope_correction_v2_4.schema.json`: standalone shape and enum constraints.
- Create `src/stock_research/research_project_v2_1/governance.py`: semantic validation and immutable canonical reading.
- Modify `src/stock_research/research_project_v2_1/layout.py`: add the governance directory property.
- Modify `src/stock_research/research_project_v2_1/schema.py`: register the new standalone schema.
- Create `tests/test_research_project_v2_1_scope_correction.py`: focused schema, semantic, drift, and forbidden-role tests.
- Create `artifacts/research_projects/v2_1/governance/stage_a_scope_correction_v1.json`: the append-only decision artifact.
- Create `docs/research_operating_layer_v2_r2b_ai_pcb_scope_correction_and_stage_a2_plan.md`: full governance decision and Stage A2 plan.
- Modify `docs/research_operating_layer_v2_r2b_ai_pcb_stage_a_acquisition.md`: append historical scope-correction notice.
- Create `artifacts/research_projects/v2_1/governance/stage_a_scope_correction_exact_allowlist.json`: exact changed-path attribution.
- Modify `tests/test_research_project_v2_1_r2b_scope_guard.py`: enforce the new allowlist and original-checkpoint immutability.

### Task 1: Add failing schema-contract tests

**Files:**
- Create: `tests/test_research_project_v2_1_scope_correction.py`
- Modify later: `artifacts/research_projects/v2_1/schema/stage_a_scope_correction_v2_4.schema.json`
- Modify later: `src/stock_research/research_project_v2_1/schema.py`

- [ ] **Step 1: Write the canonical valid-payload fixture and schema test**

The fixture must include the six global entities, the evidence-use invariants, preserved acquisition rules, Stage A2 object flow, candidate value-chain dimensions, downstream prohibitions, provenance, and a placeholder valid lowercase SHA-256.

```python
from copy import deepcopy
from pathlib import Path

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


GLOBAL_ENTITIES = (
    "NVIDIA",
    "Intel / Habana",
    "Cisco",
    "Broadcom",
    "Lightmatter",
    "Supermicro",
)


def scope_correction_payload() -> dict:
    return {
        "schema_version": "2.4.0",
        "artifact_kind": "stage_a_scope_correction",
        "decision": {
            "decision_id": "scope_correction:ai_compute_pcb_stage_a_v1",
            "decision_type": "stage_a_scope_correction",
            "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
            "investment_market_scope": "A_share",
            "original_stage": "stage_a_acquisition",
            "original_checkpoint": {
                "checkpoint_id": "acquisition_checkpoint:a5f7627d8726c9405ba67a75",
                "canonical_content_hash": "a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e",
                "file_sha256": "e2b91137df1c01a7fa7b30c8ed9cdd8b052e30ad3a57a274519fab20cb2f07ae",
            },
            "corrected_stage_role": "global_industry_reference_acquisition",
            "corrected_status": "global_industry_reference_acquisition_complete",
            "global_entities_role": "industry_reference_only",
            "global_equity_assessment_allowed": False,
            "a_share_candidate_coverage_claimed": False,
            "evidence_assessment_allowed": "industry_claim_level_only",
            "company_level_assessment_allowed": False,
            "stage_b_authorized": False,
            "next_stage": "stage_a2_a_share_supply_chain_mapping",
            "entity_classifications": [
                {
                    "entity_name": name,
                    "entity_role": "global_industry_reference",
                    "investment_candidate": False,
                    "eligible_for_a_share_review_universe": False,
                    "eligible_for_company_scoring": False,
                    "eligible_for_signal": False,
                    "eligible_for_admission": False,
                }
                for name in GLOBAL_ENTITIES
            ],
            "evidence_use_invariants": [
                "global_reference_coverage != a_share_candidate_coverage",
                "primary_source_count != evidence_sufficiency",
                "industry_claim_support != company_exposure_support",
            ],
            "preserved_acquisition_rules": [
                "blocked_attempts_do_not_count_as_acquired_evidence",
                "exact_duplicates_count_as_one_evidence_chain",
                "suspected_common_origin_is_one_provisional_chain",
                "unknown_publication_dates_remain_unknown",
                "er05_denominator_remains_open",
                "widen_redirects_remain_fail_closed",
                "network_mode_remains_direct_http_trust_env_false",
            ],
            "stage_a2_plan": {
                "stage_name": "Stage A2 — A-share Supply-chain Mapping",
                "plan_status": "planned",
                "research_only": True,
                "acquisition_started": False,
                "company_universe_generated": False,
                "object_flow": [
                    "global_technology_claim",
                    "component_or_process_requirement",
                    "value_chain_segment",
                    "a_share_candidate_hypothesis",
                    "company_specific_evidence_requirement",
                ],
                "candidate_mapping_dimensions": ["high_speed_pcb"],
                "acceptance_criteria": [
                    "industry-evidence traceability precedes candidate hypotheses"
                ],
                "forbidden_outputs": [
                    "company_score", "stock_recommendation", "signal", "admission",
                    "portfolio", "strategy", "trade",
                ],
            },
            "provenance": {
                "created_by": "Codex",
                "actor_type": "codex",
                "agent_run_id": "r2b-stage-a-scope-correction-20260721",
                "created_at": "2026-07-21T00:00:00Z",
                "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
                "review_status": "reviewed",
            },
        },
        "content_hash": "0" * 64,
    }


def test_schema_v2_4_accepts_stage_a_scope_correction() -> None:
    validate_v2_1_schema_payload(
        "stage_a_scope_correction_v2_4", scope_correction_payload()
    )
```

- [ ] **Step 2: Write parameterized schema rejection tests**

Reject a non-A-share market, enabled global equity assessment, enabled company assessment, enabled Stage B, wrong next stage, executed Stage A2 acquisition, and any true eligibility flag.

```python
@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (lambda p: p["decision"].update(investment_market_scope="US"), ["decision", "investment_market_scope"]),
        (lambda p: p["decision"].update(global_equity_assessment_allowed=True), ["decision", "global_equity_assessment_allowed"]),
        (lambda p: p["decision"].update(company_level_assessment_allowed=True), ["decision", "company_level_assessment_allowed"]),
        (lambda p: p["decision"].update(stage_b_authorized=True), ["decision", "stage_b_authorized"]),
        (lambda p: p["decision"].update(next_stage="stage_b"), ["decision", "next_stage"]),
        (lambda p: p["decision"]["stage_a2_plan"].update(acquisition_started=True), ["decision", "stage_a2_plan", "acquisition_started"]),
        (lambda p: p["decision"]["entity_classifications"][0].update(investment_candidate=True), ["decision", "entity_classifications", 0, "investment_candidate"]),
    ],
)
def test_schema_v2_4_rejects_scope_leakage(mutate, expected_path) -> None:
    payload = scope_correction_payload()
    mutate(payload)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload("stage_a_scope_correction_v2_4", payload)
    assert exc_info.value.details["path"] == expected_path
```

- [ ] **Step 3: Run the tests and observe RED**

Run:

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py
```

Expected: failure with `RESEARCH_PROJECT_V2_1_SCHEMA_NOT_FOUND` for `stage_a_scope_correction_v2_4`.

- [ ] **Step 4: Add the minimal Schema 2.4.0 and schema registration**

Add to `SCHEMA_FILES`:

```python
"stage_a_scope_correction_v2_4": "stage_a_scope_correction_v2_4.schema.json",
```

The schema uses `const` for every fixed boundary, `additionalProperties: false` throughout, exact six-entity cardinality, enums for entity names and Stage A2 dimensions, and `$ref` to `definitions_v2_1.schema.json#/$defs/provenance`.

The top-level required fields are:

```json
["schema_version", "artifact_kind", "decision", "content_hash"]
```

The fixed top-level values are:

```json
{
  "schema_version": {"const": "2.4.0"},
  "artifact_kind": {"const": "stage_a_scope_correction"},
  "content_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
}
```

- [ ] **Step 5: Run the focused schema tests and observe GREEN**

Run:

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py
```

Expected: all current tests pass.

- [ ] **Step 6: Commit the schema contract**

```bash
rtk git add artifacts/research_projects/v2_1/schema/stage_a_scope_correction_v2_4.schema.json src/stock_research/research_project_v2_1/schema.py tests/test_research_project_v2_1_scope_correction.py
rtk git commit -m "feat: define stage a scope correction schema"
```

### Task 2: Add semantic drift validation

**Files:**
- Create: `src/stock_research/research_project_v2_1/governance.py`
- Modify: `src/stock_research/research_project_v2_1/layout.py`
- Modify: `tests/test_research_project_v2_1_scope_correction.py`

- [ ] **Step 1: Write failing tests for checkpoint binding and entity completeness**

Use a temporary layered layout containing a canonical checkpoint fixture. Tests must cover:

```python
def test_validate_scope_correction_binds_checkpoint_id_and_both_hashes(tmp_path: Path) -> None:
    ...


@pytest.mark.parametrize(
    "field",
    ["canonical_content_hash", "file_sha256"],
)
def test_validate_scope_correction_rejects_checkpoint_drift(tmp_path: Path, field: str) -> None:
    ...


@pytest.mark.parametrize("entity_name", GLOBAL_ENTITIES)
def test_validate_scope_correction_requires_every_global_reference_entity(
    tmp_path: Path, entity_name: str
) -> None:
    ...
```

The checkpoint fixture must be written with `canonical_bytes`, and its embedded checkpoint `content_hash` must be computed with `content_sha256(checkpoint, excluded_paths={("content_hash",)})`.

- [ ] **Step 2: Write failing tests for artifact canonical hash and downstream terms**

```python
@pytest.mark.parametrize(
    "forbidden",
    ["company_score", "stock_recommendation", "signal", "admission", "portfolio", "strategy", "trade"],
)
def test_validate_scope_correction_rejects_missing_downstream_prohibition(
    tmp_path: Path, forbidden: str
) -> None:
    ...


def test_validate_scope_correction_rejects_content_hash_mismatch(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 3: Run the semantic tests and observe RED**

Run:

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py
```

Expected: import failure because `research_project_v2_1.governance` does not exist.

- [ ] **Step 4: Implement the focused validator**

Create:

```python
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import read_layered_canonical_json
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


REQUIRED_GLOBAL_ENTITIES = {
    "NVIDIA", "Intel / Habana", "Cisco", "Broadcom", "Lightmatter", "Supermicro"
}
REQUIRED_FORBIDDEN_OUTPUTS = {
    "company_score", "stock_recommendation", "signal", "admission",
    "portfolio", "strategy", "trade",
}


def _error(message: str, *, field: str, actual: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_SCOPE_CORRECTION_INVALID",
        details={"field": field, "actual": actual},
    )


def validate_stage_a_scope_correction(
    payload: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    copied = deepcopy(payload)
    validate_v2_1_schema_payload(
        "stage_a_scope_correction_v2_4", copied, layout=layout
    )
    expected_hash = content_sha256(copied, excluded_paths={("content_hash",)})
    if copied["content_hash"] != expected_hash:
        raise _error("Scope correction content hash mismatch", field="content_hash", actual=copied["content_hash"])

    effective = LayeredResearchLayout.default() if layout is None else layout
    reference = copied["decision"]["original_checkpoint"]
    relative = Path("acquisition/checkpoints") / f"{reference['checkpoint_id']}.json"
    checkpoint_path = effective.root / relative
    checkpoint_wrapper = read_layered_canonical_json(relative, layout=effective)
    checkpoint = checkpoint_wrapper["acquisition_checkpoint"]
    if checkpoint["checkpoint_id"] != reference["checkpoint_id"]:
        raise _error("Original checkpoint ID mismatch", field="original_checkpoint.checkpoint_id", actual=checkpoint["checkpoint_id"])
    if checkpoint["content_hash"] != reference["canonical_content_hash"]:
        raise _error("Original checkpoint canonical hash mismatch", field="original_checkpoint.canonical_content_hash", actual=checkpoint["content_hash"])
    file_hash = sha256(checkpoint_path.read_bytes()).hexdigest()
    if file_hash != reference["file_sha256"]:
        raise _error("Original checkpoint file hash mismatch", field="original_checkpoint.file_sha256", actual=file_hash)

    entities = {item["entity_name"]: item for item in copied["decision"]["entity_classifications"]}
    if set(entities) != REQUIRED_GLOBAL_ENTITIES:
        raise _error("Global reference entity set mismatch", field="entity_classifications", actual=sorted(entities))
    if set(copied["decision"]["stage_a2_plan"]["forbidden_outputs"]) != REQUIRED_FORBIDDEN_OUTPUTS:
        raise _error("Stage A2 downstream prohibitions mismatch", field="stage_a2_plan.forbidden_outputs", actual=copied["decision"]["stage_a2_plan"]["forbidden_outputs"])
    return copied
```

Add to `LayeredResearchLayout`:

```python
@property
def governance_dir(self) -> Path:
    return self.root / "governance"
```

- [ ] **Step 5: Run semantic tests and observe GREEN**

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit semantic validation**

```bash
rtk git add src/stock_research/research_project_v2_1/governance.py src/stock_research/research_project_v2_1/layout.py tests/test_research_project_v2_1_scope_correction.py
rtk git commit -m "feat: validate stage a scope governance"
```

### Task 3: Create and validate the append-only governance artifact

**Files:**
- Create: `artifacts/research_projects/v2_1/governance/stage_a_scope_correction_v1.json`
- Modify: `tests/test_research_project_v2_1_scope_correction.py`

- [ ] **Step 1: Add a failing repository-artifact test**

```python
def test_repository_scope_correction_artifact_is_valid_and_checkpoint_is_unchanged() -> None:
    layout = LayeredResearchLayout.default()
    path = layout.governance_dir / "stage_a_scope_correction_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_stage_a_scope_correction(payload, layout=layout)
    checkpoint = layout.acquisition_checkpoints_dir / "acquisition_checkpoint:a5f7627d8726c9405ba67a75.json"
    wrapper = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert wrapper["acquisition_checkpoint"]["content_hash"] == "a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e"
    assert sha256(checkpoint.read_bytes()).hexdigest() == "e2b91137df1c01a7fa7b30c8ed9cdd8b052e30ad3a57a274519fab20cb2f07ae"
```

- [ ] **Step 2: Run the repository test and observe RED**

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py::test_repository_scope_correction_artifact_is_valid_and_checkpoint_is_unchanged
```

Expected: `FileNotFoundError` for the governance artifact.

- [ ] **Step 3: Create the canonical artifact**

Start from the tested fixture, replace the placeholder hash with:

```python
payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
```

Write the resulting bytes using RFC 8785 canonical JSON. The Stage A2 candidate dimensions must include every category requested in the approved specification, but the artifact must not contain an A-share company name or any executed acquisition object.

- [ ] **Step 4: Run the repository test and observe GREEN**

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit the governance artifact**

```bash
rtk git add artifacts/research_projects/v2_1/governance/stage_a_scope_correction_v1.json tests/test_research_project_v2_1_scope_correction.py
rtk git commit -m "data: classify ai pcb stage a as industry reference"
```

### Task 4: Document the correction and Stage A2 plan

**Files:**
- Create: `docs/research_operating_layer_v2_r2b_ai_pcb_scope_correction_and_stage_a2_plan.md`
- Modify: `docs/research_operating_layer_v2_r2b_ai_pcb_stage_a_acquisition.md`
- Modify: `tests/test_research_project_v2_1_scope_correction.py`

- [ ] **Step 1: Write failing documentation-boundary tests**

The tests read both documents and require the exact statements that Stage A remains technically valid, market scope is A-share, global entities are references only, industry-level assessment is permitted, company-level assessment and Stage B are prohibited, and Stage A2 is planned but not started.

```python
def test_scope_correction_documents_preserve_history_and_state_boundaries() -> None:
    stage_a = (REPOSITORY_ROOT / "docs/research_operating_layer_v2_r2b_ai_pcb_stage_a_acquisition.md").read_text()
    plan = (REPOSITORY_ROOT / "docs/research_operating_layer_v2_r2b_ai_pcb_scope_correction_and_stage_a2_plan.md").read_text()
    for phrase in (
        "global_industry_reference_acquisition",
        "investment_market_scope = A_share",
        "industry_claim_level_only",
        "company_level_assessment_allowed = false",
        "stage_b_authorized = false",
        "Stage A2 — A-share Supply-chain Mapping",
    ):
        assert phrase in stage_a
        assert phrase in plan
    assert "Stage A2 acquisition has not started" in plan
```

- [ ] **Step 2: Run and observe RED**

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py::test_scope_correction_documents_preserve_history_and_state_boundaries
```

Expected: missing independent plan document and missing appended correction section.

- [ ] **Step 3: Add the independent plan and append the historical notice**

The independent document contains the governance decision, evidence-use split, six entity roles, Stage A2 inputs, outputs, object flow, candidate dimensions, acceptance criteria, prohibited outputs, and stop condition.

Append a new `## Scope Correction` section to the end of the existing acquisition report. Do not alter any earlier line.

- [ ] **Step 4: Run and observe GREEN**

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit documentation**

```bash
rtk git add docs/research_operating_layer_v2_r2b_ai_pcb_stage_a_acquisition.md docs/research_operating_layer_v2_r2b_ai_pcb_scope_correction_and_stage_a2_plan.md tests/test_research_project_v2_1_scope_correction.py
rtk git commit -m "docs: define ai pcb stage a2 mapping boundary"
```

### Task 5: Lock exact scope attribution

**Files:**
- Create: `artifacts/research_projects/v2_1/governance/stage_a_scope_correction_exact_allowlist.json`
- Modify: `tests/test_research_project_v2_1_r2b_scope_guard.py`
- Modify: `tests/test_research_project_v2_1_scope_correction.py`

- [ ] **Step 1: Write failing scope-guard tests**

The allowlist baseline is `ae4e70e`. The allowed implementation paths are exactly the files listed in this plan plus the committed design and plan documents. The test must exclude the original checkpoint and all acquisition history from the allowlist.

```python
def test_scope_correction_uses_exact_allowlist_and_excludes_acquisition_history() -> None:
    payload = json.loads((REPOSITORY_ROOT / "artifacts/research_projects/v2_1/governance/stage_a_scope_correction_exact_allowlist.json").read_text())
    assert payload["baseline_commit"] == "ae4e70e"
    assert "artifacts/research_projects/v2_1/acquisition/checkpoints/acquisition_checkpoint:a5f7627d8726c9405ba67a75.json" not in payload["paths"]
    changed = set(_git("diff", "--name-only", "ae4e70e..HEAD").stdout.splitlines())
    assert changed <= set(payload["paths"])
```

Also add rejection examples for signal, admission, scoring, portfolio, strategy, database, API, dashboard, V1, and other pilots.

- [ ] **Step 2: Run and observe RED**

```bash
rtk pytest -q tests/test_research_project_v2_1_r2b_scope_guard.py tests/test_research_project_v2_1_scope_correction.py
```

Expected: missing allowlist artifact or changed paths outside the old Stage A allowlist.

- [ ] **Step 3: Add the machine-readable allowlist and update the guard**

The allowlist contains:

```json
{
  "allowlist_id": "scope_allowlist:r2b_ai_pcb_stage_a_scope_correction",
  "baseline_commit": "ae4e70e",
  "phase": "r2b_ai_compute_pcb_stage_a_scope_correction",
  "schema_version": "1.0.0",
  "paths": [],
  "forbidden_prefixes": []
}
```

Populate `paths` with the exact files from this implementation and `forbidden_prefixes` with V1, acquisition history, projects/versions, other pilots, dashboard, API, database, signal, admission, portfolio, watchlist, strategy, and rating paths.

Because the pre-implementation design commit is after `ae4e70e`, include both the design spec and this implementation plan in the exact path list.

- [ ] **Step 4: Run and observe GREEN**

```bash
rtk pytest -q tests/test_research_project_v2_1_r2b_scope_guard.py tests/test_research_project_v2_1_scope_correction.py
```

Expected: all focused and scope-guard tests pass.

- [ ] **Step 5: Commit scope attribution**

```bash
rtk git add artifacts/research_projects/v2_1/governance/stage_a_scope_correction_exact_allowlist.json tests/test_research_project_v2_1_r2b_scope_guard.py tests/test_research_project_v2_1_scope_correction.py
rtk git commit -m "test: lock ai pcb scope correction attribution"
```

### Task 6: Independent audit and final verification

**Files:**
- No implementation files unless verification reveals a defect.

- [ ] **Step 1: Verify original checkpoint immutability**

```bash
rtk git diff --exit-code ae4e70e -- artifacts/research_projects/v2_1/acquisition/checkpoints/'acquisition_checkpoint:a5f7627d8726c9405ba67a75.json'
rtk sha256sum artifacts/research_projects/v2_1/acquisition/checkpoints/'acquisition_checkpoint:a5f7627d8726c9405ba67a75.json'
```

Expected byte hash:

```text
e2b91137df1c01a7fa7b30c8ed9cdd8b052e30ad3a57a274519fab20cb2f07ae
```

Then parse the checkpoint and verify its embedded canonical content hash is:

```text
a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e
```

- [ ] **Step 2: Run focused governance tests**

```bash
rtk pytest -q tests/test_research_project_v2_1_scope_correction.py tests/test_research_project_v2_1_r2b_scope_guard.py tests/test_research_project_v2_1_acquisition_schema.py tests/test_research_project_v2_1_acquisition_normalize.py tests/test_research_project_v2_1_acquisition_storage.py
```

Expected: zero failures.

- [ ] **Step 3: Run V2 and R1-R2 compatibility regression**

Use the repository's established V2/R1-R2 command from the prior Stage A verification. Record exact pass count and exit code; do not reuse the historical `1306 passed` result.

- [ ] **Step 4: Run V1, Theme Research, and Dashboard regression**

Use the repository's established V1/Theme/Dashboard command from the prior Stage A verification. Record exact pass count and exit code; do not reuse the historical `449 passed` result.

- [ ] **Step 5: Parse and validate all JSON/JSONL**

Run the existing repository JSON/JSONL validation command and explicitly validate `stage_a_scope_correction_v1.json` with the new schema and semantic validator.

- [ ] **Step 6: Audit sensitive data, partial files, and scope leakage**

```bash
rtk rg -n -i '(api[_-]?key|password|cookie|authorization:|bearer |proxy.*@)' artifacts/research_projects/v2_1/governance docs/research_operating_layer_v2_r2b_ai_pcb_scope_correction_and_stage_a2_plan.md || true
rtk find artifacts/research_projects/v2_1 -type f \( -name '*.part' -o -name '*.tmp' \)
rtk git diff --name-only ae4e70e..HEAD
rtk git diff --check ae4e70e..HEAD
```

Expected: no sensitive values, no partial files, only allowlisted paths, and no whitespace errors.

- [ ] **Step 7: Review the implementation against every acceptance criterion**

Confirm in order:

1. original checkpoint bytes and embedded hash unchanged;
2. acquisition artifacts not deleted;
3. append-only correction present and valid;
4. all six global entities reference-only;
5. A-share is the only investment market;
6. industry assessment only;
7. company assessment false;
8. Stage B false;
9. Stage A2 planned and not started;
10. no downstream or company artifacts;
11. all regressions pass;
12. exact attribution holds.

- [ ] **Step 8: Commit any verification-only correction, then rerun all affected commands**

Do not claim completion until every verification command has been rerun after the final commit.

- [ ] **Step 9: Confirm clean worktree and report final commit**

```bash
rtk git status --short
rtk git rev-parse HEAD
```

Expected: empty status output and one final commit SHA.
