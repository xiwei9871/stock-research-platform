# Research Operating Layer V2 R1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the offline, artifact-first R1 baseline for Research Operating Layer V2 without modifying V1 themes, production databases, existing APIs, or Dashboard behavior.

**Architecture:** Add a focused `stock_research.research_project_v2` package that owns schema validation, immutable version storage, semantic validation, local V1 reference audits, staged quality gates, version diffing, and CLI presentation. Canonical R1 data lives only under `artifacts/research_projects/v2`; the four pilot projects are research-design snapshots and contain no supported claims, completed evidence assessments, company-capture conclusions, or investment judgments.

**Tech Stack:** Python 3.11+, standard library, `jsonschema`, `rfc8785`, pytest, JSON Schema Draft 2020-12, repository JSON artifacts.

---

## Scope Boundaries

This plan must not:

- modify any file under `artifacts/theme_decomposition/`;
- modify any file under `artifacts/technology_industry_catalog/`;
- modify `src/stock_research/dashboard/`;
- modify `dashboard/`;
- execute or add a production database migration;
- add Research Project API routes;
- add a Research Project Dashboard workspace;
- write to `research_case`, review, publication, watchlist, or strategy tables;
- generate supported claims, completed evidence assessments, company-capture conclusions, or investment recommendations for the four pilots.

## File Structure

Create focused package files:

```text
src/stock_research/research_project_v2/
├── __init__.py          public read/validate API
├── canonical.py         RFC 8785 canonicalization and SHA-256
├── cli.py               argparse commands and exit-code mapping
├── diff.py              stable-ID version comparison
├── errors.py            domain errors and stable codes
├── gates.py             Design/Evidence/Publication gates
├── layout.py            repository paths and file discovery
├── loader.py            identity/version/event/manifest/index loading
├── references.py        local namespace resolvers and drift audit
├── semantic.py          cross-object and graph validation
└── summary.py           deterministic project/index summaries
```

Create schemas and artifacts:

```text
artifacts/research_projects/v2/
├── schema/
│   ├── definitions_v2.schema.json
│   ├── research_event_v2.schema.json
│   ├── research_project_identity_v2.schema.json
│   ├── research_project_index_v2.schema.json
│   └── research_version_v2.schema.json
├── projects/<four-project-slugs>/
│   ├── project.json
│   ├── events/events.jsonl
│   ├── version_manifest.jsonl
│   └── versions/v0.1.0.json
├── index/research_project_index_v2.json
└── fixtures/{valid,invalid}/
```

Tests:

```text
tests/test_research_project_v2_schema.py
tests/test_research_project_v2_storage.py
tests/test_research_project_v2_semantic.py
tests/test_research_project_v2_references.py
tests/test_research_project_v2_gates.py
tests/test_research_project_v2_diff.py
tests/test_research_project_v2_cli.py
tests/test_research_project_v2_pilots.py
```

Modify only:

```text
pyproject.toml
src/stock_research/cli.py
docs/research_operating_layer_v2_goal_and_roadmap.md
```

## Task 1: Package Shell, Dependencies, Paths, And Errors

**Files:**

- Modify: `pyproject.toml`
- Create: `src/stock_research/research_project_v2/__init__.py`
- Create: `src/stock_research/research_project_v2/errors.py`
- Create: `src/stock_research/research_project_v2/layout.py`
- Test: `tests/test_research_project_v2_storage.py`

- [ ] **Step 1: Write the failing package-layout test**

```python
from pathlib import Path

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.layout import ResearchProjectLayout


def test_default_layout_points_at_versioned_artifact_root():
    layout = ResearchProjectLayout.default()

    assert layout.root.as_posix().endswith("artifacts/research_projects/v2")
    assert layout.schema_dir == layout.root / "schema"
    assert layout.projects_dir == layout.root / "projects"
    assert layout.index_path == layout.root / "index/research_project_index_v2.json"


def test_domain_error_exposes_stable_code_and_details():
    error = ResearchProjectV2Error(
        "version not found",
        code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
        details={"version": "0.1.0"},
    )

    assert error.code == "RESEARCH_PROJECT_VERSION_NOT_FOUND"
    assert error.details == {"version": "0.1.0"}
```

- [ ] **Step 2: Run the tests and confirm the import fails**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_storage.py -q
```

Expected: FAIL with `ModuleNotFoundError: stock_research.research_project_v2`.

- [ ] **Step 3: Add runtime dependencies**

Add to `pyproject.toml` project dependencies:

```toml
  "jsonschema>=4.26,<5",
  "rfc8785>=0.1.4,<0.2",
```

Install the worktree in the shared development environment:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pip install -e '.[dev]'
```

Expected: editable install completes and both imports succeed.

- [ ] **Step 4: Implement errors and layout**

`errors.py`:

```python
from __future__ import annotations

from typing import Any


class ResearchProjectV2Error(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}
```

`layout.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ResearchProjectLayout:
    root: Path

    @classmethod
    def default(cls) -> "ResearchProjectLayout":
        return cls(REPOSITORY_ROOT / "artifacts" / "research_projects" / "v2")

    @property
    def schema_dir(self) -> Path:
        return self.root / "schema"

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def index_path(self) -> Path:
        return self.root / "index" / "research_project_index_v2.json"

    def project_dir(self, project_slug: str) -> Path:
        return self.projects_dir / project_slug
```

`__init__.py` initially exports `ResearchProjectV2Error` and `ResearchProjectLayout`.

- [ ] **Step 5: Run the focused test**

Run the Task 1 pytest command again.

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
rtk git add pyproject.toml src/stock_research/research_project_v2 \
  tests/test_research_project_v2_storage.py
rtk git commit -m "feat: scaffold research project v2 package"
```

## Task 2: JSON Schemas And Schema Validation

**Files:**

- Create: `artifacts/research_projects/v2/schema/definitions_v2.schema.json`
- Create: `artifacts/research_projects/v2/schema/research_project_identity_v2.schema.json`
- Create: `artifacts/research_projects/v2/schema/research_version_v2.schema.json`
- Create: `artifacts/research_projects/v2/schema/research_event_v2.schema.json`
- Create: `artifacts/research_projects/v2/schema/research_project_index_v2.schema.json`
- Create: `src/stock_research/research_project_v2/loader.py`
- Test: `tests/test_research_project_v2_schema.py`

- [ ] **Step 1: Write failing schema tests**

```python
import json

import pytest

from stock_research.research_project_v2.loader import validate_schema_payload
from stock_research.research_project_v2.errors import ResearchProjectV2Error


def test_identity_schema_accepts_pointer_only_identity(sample_identity):
    validate_schema_payload("research_project_identity_v2", sample_identity)


def test_version_schema_rejects_supported_claim_in_design_fixture(sample_version):
    broken = json.loads(json.dumps(sample_version))
    broken["snapshot"]["claims"][0]["claim_status"] = "supported"

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_schema_payload("research_version_v2", broken)

    assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"


def test_event_schema_requires_append_only_event_identity(sample_event):
    broken = {key: value for key, value in sample_event.items() if key != "event_id"}

    with pytest.raises(ResearchProjectV2Error):
        validate_schema_payload("research_event_v2", broken)
```

Define `sample_identity`, `sample_version`, and `sample_event` fixtures in this test file with these exact identities: project `research_project:fixture`, version `research_version:fixture:0.1.0`, questions `question:primary` and `question:counterfactual`, claims `claim:primary` and `claim:counter`, requirements `requirement:primary` and `requirement:counter`, metric `metric:primary`, condition `condition:primary`, and event `research_event:fixture:created`. Set the version to `research_design`, `research_ready`, `requirements_defined`, `unavailable`, and `not_assessed`; keep `evidence_assessments` and `company_capture_assessments` empty.

- [ ] **Step 2: Run tests and verify failure**

Expected: imports or missing schema files fail.

- [ ] **Step 3: Create common definitions schema**

Use Draft 2020-12. The common schema must define these reusable `$defs`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "definitions_v2.schema.json",
  "$defs": {
    "semantic_version": {
      "type": "string",
      "pattern": "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$"
    },
    "sha256": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$"
    },
    "provenance": {
      "type": "object",
      "additionalProperties": false,
      "required": ["created_by", "actor_type", "agent_run_id", "created_at", "created_in_version", "review_status"],
      "properties": {
        "created_by": {"type": "string", "minLength": 1},
        "actor_type": {"enum": ["human", "codex", "automated_pipeline", "imported"]},
        "agent_run_id": {"type": ["string", "null"]},
        "created_at": {"type": "string", "format": "date-time"},
        "created_in_version": {"type": "string", "minLength": 1},
        "review_status": {"enum": ["unreviewed", "pending_review", "reviewed", "rejected"]}
      }
    },
    "object_lifecycle": {
      "enum": ["active", "retired", "superseded", "removed_from_scope"]
    },
    "target_type": {
      "enum": ["research_project", "research_question", "research_claim", "causal_edge", "company_capture"]
    },
    "hash_scope": {
      "enum": ["entire_object", "selected_fields", "source_content", "metadata_only"]
    }
  }
}
```

- [ ] **Step 4: Create the four top-level schemas**

Implement the exact required fields and enums from the approved design. Every object uses `additionalProperties: false`. `research_version_v2.schema.json` must conditionally enforce the research-design restrictions:

```json
{
  "if": {"properties": {"creation_stage": {"const": "research_design"}}},
  "then": {
    "properties": {
      "snapshot": {
        "properties": {
          "evidence_stage": {"const": "requirements_defined"},
          "conclusion_status": {"const": "unavailable"},
          "investment_status": {"const": "not_assessed"},
          "evidence_assessments": {"maxItems": 0},
          "company_capture_assessments": {"maxItems": 0},
          "claims": {
            "items": {
              "properties": {
                "epistemic_type": {"const": "hypothesis"},
                "claim_status": {"enum": ["hypothesis", "under_test"]}
              }
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 5: Implement schema loading and validation**

```python
import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

from .errors import ResearchProjectV2Error
from .layout import ResearchProjectLayout


SCHEMA_FILES = {
    "research_project_identity_v2": "research_project_identity_v2.schema.json",
    "research_version_v2": "research_version_v2.schema.json",
    "research_event_v2": "research_event_v2.schema.json",
    "research_project_index_v2": "research_project_index_v2.schema.json",
}


@lru_cache(maxsize=None)
def _schema_bundle(schema_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_dir = ResearchProjectLayout.default().schema_dir
    schema = json.loads((schema_dir / SCHEMA_FILES[schema_name]).read_text(encoding="utf-8"))
    definitions = json.loads((schema_dir / "definitions_v2.schema.json").read_text(encoding="utf-8"))
    return schema, definitions


def validate_schema_payload(schema_name: str, payload: dict[str, Any]) -> None:
    schema, definitions = _schema_bundle(schema_name)
    resolver = RefResolver.from_schema(
        schema,
        store={"definitions_v2.schema.json": definitions},
    )
    errors = sorted(
        Draft202012Validator(schema, resolver=resolver, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        raise ResearchProjectV2Error(
            first.message,
            code="RESEARCH_PROJECT_SCHEMA_INVALID",
            details={"path": list(first.absolute_path), "schema": schema_name},
        )
```

Use `RefResolver` for R1 and suppress only its library deprecation warning in the focused schema tests. Replacing it with `referencing.Registry` is outside R1 unless `RefResolver` is removed by the declared `jsonschema<5` dependency.

- [ ] **Step 6: Run schema tests**

Expected: all schema tests pass.

- [ ] **Step 7: Commit**

```bash
rtk git add artifacts/research_projects/v2/schema \
  src/stock_research/research_project_v2/loader.py \
  tests/test_research_project_v2_schema.py
rtk git commit -m "feat: define research project v2 schemas"
```

## Task 3: Canonical Hashing, Immutable Storage, Events, And Index

**Files:**

- Create: `src/stock_research/research_project_v2/canonical.py`
- Modify: `src/stock_research/research_project_v2/loader.py`
- Test: `tests/test_research_project_v2_storage.py`

- [ ] **Step 1: Add failing canonical and storage tests**

```python
from copy import deepcopy
import json

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.loader import load_project, load_version
from stock_research.research_project_v2.errors import ResearchProjectV2Error


def test_content_hash_is_order_and_whitespace_independent():
    left = {"b": 2, "a": [1, {"x": "研究"}]}
    right = json.loads('{ "a": [1, {"x":"研究"}], "b": 2 }')
    assert content_sha256(left) == content_sha256(right)


def test_version_hash_excludes_its_own_content_hash(sample_version):
    first = deepcopy(sample_version)
    second = deepcopy(sample_version)
    first["content_hash"] = "0" * 64
    second["content_hash"] = "f" * 64
    assert content_sha256(first, excluded_paths={("content_hash",)}) == content_sha256(
        second,
        excluded_paths={("content_hash",)},
    )


def test_loader_rejects_manifest_hash_mismatch(tmp_project_layout):
    version_path = tmp_project_layout.projects_dir / "demo/versions/v0.1.0.json"
    payload = json.loads(version_path.read_text(encoding="utf-8"))
    payload["change_summary"] = "silently changed"
    version_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("demo", "0.1.0", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"
```

- [ ] **Step 2: Verify the tests fail**

Expected: missing canonical and storage functions.

- [ ] **Step 3: Implement RFC 8785 hashing**

```python
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Iterable

import rfc8785


def _drop_path(payload: Any, path: tuple[str, ...]) -> None:
    current = payload
    for segment in path[:-1]:
        if not isinstance(current, dict) or segment not in current:
            return
        current = current[segment]
    if isinstance(current, dict):
        current.pop(path[-1], None)


def canonical_bytes(
    payload: Any,
    *,
    excluded_paths: Iterable[tuple[str, ...]] = (),
) -> bytes:
    normalized = deepcopy(payload)
    for path in excluded_paths:
        _drop_path(normalized, path)
    return rfc8785.dumps(normalized)


def content_sha256(
    payload: Any,
    *,
    excluded_paths: Iterable[tuple[str, ...]] = (),
) -> str:
    return hashlib.sha256(canonical_bytes(payload, excluded_paths=excluded_paths)).hexdigest()
```

- [ ] **Step 4: Implement project, version, event, manifest, and index loading**

Implement these exact public signatures: `list_project_slugs(*, layout=None)`, `load_project(project_slug, *, layout=None)`, `list_versions(project_slug, *, layout=None)`, `load_version(project_slug, semantic_version=None, *, layout=None)`, `load_events(project_slug, *, layout=None)`, and `load_index(*, layout=None)`. Annotate each optional layout as `ResearchProjectLayout | None`; list functions return sorted lists, object loaders return dictionaries, and missing paths raise `RESEARCH_PROJECT_NOT_FOUND` or `RESEARCH_PROJECT_VERSION_NOT_FOUND`.

`load_version` must:

1. resolve `current_version` when version is omitted;
2. validate JSON Schema;
3. verify the embedded hash excluding `content_hash`;
4. find the matching append-only manifest row;
5. verify path, version ID, parent ID, and content hash match;
6. raise `RESEARCH_PROJECT_IMMUTABILITY_VIOLATION` for any mismatch.

`load_events` validates every non-empty JSONL line and rejects duplicate event IDs with `RESEARCH_PROJECT_DUPLICATE_EVENT_ID`.

- [ ] **Step 5: Run storage tests**

Expected: canonical, pointer, version, event, and manifest tests pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/stock_research/research_project_v2/canonical.py \
  src/stock_research/research_project_v2/loader.py \
  tests/test_research_project_v2_storage.py
rtk git commit -m "feat: load immutable research project versions"
```

## Task 4: Semantic Validation And Object Identity

**Files:**

- Create: `src/stock_research/research_project_v2/semantic.py`
- Test: `tests/test_research_project_v2_semantic.py`

- [ ] **Step 1: Write failing semantic tests**

Create one test per row in this mutation matrix:

| Test mutation | Expected code |
|---|---|
| `question:primary` depends on `question:counterfactual` and the latter depends on the former | `RESEARCH_PROJECT_QUESTION_DEPENDENCY_CYCLE` |
| A tree node names a missing `parent_tree_node_id` | `RESEARCH_PROJECT_TREE_PARENT_NOT_FOUND` |
| A claim relation names `claim:missing` | `RESEARCH_PROJECT_CLAIM_RELATION_TARGET_NOT_FOUND` |
| A requirement uses target type `research_claim` with `target_id=claim:missing` | `RESEARCH_PROJECT_EVIDENCE_TARGET_NOT_FOUND` |
| A claim context reference resolves a reference with role `supports` | `RESEARCH_PROJECT_CONTEXT_REFERENCE_ROLE_INVALID` |
| A causal edge names `causal_node:missing` | `RESEARCH_PROJECT_CAUSAL_NODE_NOT_FOUND` |
| Two causal edges form a cycle without a shared `feedback_loop_id` | `RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE` |
| A claim supersedes itself or a missing claim | `RESEARCH_PROJECT_SUPERSEDES_CLAIM_INVALID` |
| Two claims use the same `claim_id` | `RESEARCH_PROJECT_DUPLICATE_OBJECT_ID` |

Each test mutates one valid fixture and asserts the exact stable error code, for example:

```python
with pytest.raises(ResearchProjectV2Error) as exc_info:
    validate_version_semantics(broken)
assert exc_info.value.code == "RESEARCH_PROJECT_QUESTION_DEPENDENCY_CYCLE"
```

- [ ] **Step 2: Verify all tests fail**

- [ ] **Step 3: Implement semantic validation**

Public entry point:

```python
def validate_version_semantics(version: dict[str, Any]) -> None:
    snapshot = version["snapshot"]
    _require_unique_ids(snapshot)
    _validate_question_trees(snapshot)
    _validate_claims(snapshot)
    _validate_evidence_targets(snapshot)
    _validate_context_references(snapshot)
    _validate_causal_graph(snapshot)
    _validate_metric_targets(snapshot)
    _validate_first_design_snapshot(version)
```

Implement Kahn topological sorting for question dependencies. Causal cycles are allowed only when every edge participating in the detected cycle has the same non-empty `feedback_loop_id`; otherwise raise `RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE`.

Use a shared target registry:

```python
TARGET_COLLECTIONS = {
    "research_project": None,
    "research_question": "questions",
    "research_claim": "claims",
    "causal_edge": "causal_edges",
    "company_capture": "company_capture_assessments",
}
```

Validate `context_reference_ids` only resolve references with role `definition`, `background`, or `scope_context`.

- [ ] **Step 4: Run semantic tests**

Expected: all semantic tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/research_project_v2/semantic.py \
  tests/test_research_project_v2_semantic.py
rtk git commit -m "feat: validate research project semantics"
```

## Task 5: Local V1 Reference Resolvers And Drift Audit

**Files:**

- Create: `src/stock_research/research_project_v2/references.py`
- Test: `tests/test_research_project_v2_references.py`

- [ ] **Step 1: Write failing reference tests**

Test these statuses:

```text
resolved
missing
type_mismatch
version_mismatch
hash_mismatch
deprecated
duplicate
unresolvable
```

Use real V1 artifacts for one theme, one node, one source, one company mapping, one catalog chain, and one catalog node. Do not edit those artifacts.

Create one test for each exact case: a real Theme reference resolves with `entire_object`; `selected_fields` without `hash_fields` returns `RESEARCH_PROJECT_REFERENCE_HASH_FIELDS_REQUIRED`; a deliberately changed expected hash returns `hash_mismatch` with expected, actual, algorithm, and scope; a missing node returns `missing` while the input dictionary remains byte-for-byte equal to its deep copy; duplicate namespace/type/id/role references return `duplicate`; and an unarchived `external_document` returns `unresolvable`.

- [ ] **Step 2: Verify tests fail**

- [ ] **Step 3: Implement resolver registry**

```python
@dataclass(frozen=True)
class ResolvedReference:
    namespace: str
    object_type: str
    object_id: str
    version: str | None
    payload: dict[str, Any]
    deprecated: bool = False


Resolver = Callable[[dict[str, Any]], ResolvedReference | None]


RESOLVERS: dict[str, Resolver] = {
    "theme_research_v1": resolve_theme_research_v1,
    "industry_catalog_v1": resolve_industry_catalog_v1,
}
```

`resolve_theme_research_v1` supports `v1_theme`, `v1_theme_node`, `v1_source`, `v1_claim`, and `v1_company_mapping`. `resolve_industry_catalog_v1` supports `industry_catalog_chain` and `industry_catalog_node`.

Implement hash scopes:

```python
def reference_payload(payload: dict[str, Any], reference: dict[str, Any]) -> Any:
    scope = reference["hash_scope"]
    if scope == "entire_object":
        return payload
    if scope == "selected_fields":
        return {path: resolve_json_pointer(payload, path) for path in reference["hash_fields"]}
    if scope == "metadata_only":
        return payload.get("metadata", {})
    raise ResearchProjectV2Error(
        "source_content requires an archived source payload",
        code="RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE",
    )
```

Public function:

```python
def audit_references(version: dict[str, Any]) -> dict[str, Any]:
    references = version["snapshot"]["references"]
    issues = []
    resolved_count = 0
    seen = set()
    for reference in references:
        key = (
            reference["reference_namespace"],
            reference["reference_type"],
            reference["reference_object_id"],
            reference["reference_role"],
        )
        if key in seen:
            issues.append({"reference_id": reference["reference_id"], "status": "duplicate"})
            continue
        seen.add(key)
        resolver = RESOLVERS.get(reference["reference_namespace"])
        if resolver is None:
            issues.append({"reference_id": reference["reference_id"], "status": "unresolvable"})
            continue
        resolved = resolver(reference)
        issue = compare_reference(reference, resolved)
        if issue is None:
            resolved_count += 1
        else:
            issues.append(issue)
    return {
        "status": "pass" if not issues else "fail",
        "total": len(references),
        "resolved": resolved_count,
        "issues": issues,
    }
```

Audit never rewrites a reference or version.

- [ ] **Step 4: Run reference tests**

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/research_project_v2/references.py \
  tests/test_research_project_v2_references.py
rtk git commit -m "feat: audit research project references"
```

## Task 6: Staged Quality Gates

**Files:**

- Create: `src/stock_research/research_project_v2/gates.py`
- Test: `tests/test_research_project_v2_gates.py`

- [ ] **Step 1: Write failing Design Gate tests**

Create a passing test for the valid design fixture. Then create one mutation test for each required check: clear `excluded_scope`; clear `routing_reasons`; remove the requirement targeting `question:primary`; remove the counter claim and its relation; set the primary claim to `supported`; append one evidence assessment; and append one company-capture assessment. Assert the exact check code and overall `fail` status for each mutation.

Add `test_evidence_gate_is_not_applicable_to_research_design` and `test_publication_gate_is_not_applicable_to_research_design`. Both pass the valid design fixture to `evaluate_gate`; assert `not_applicable`, assert the check list contains `GATE_CREATION_STAGE_NOT_APPLICABLE`, and assert neither result contains a passing evidence or publication check.

- [ ] **Step 2: Verify tests fail**

- [ ] **Step 3: Implement deterministic gate result types**

```python
@dataclass(frozen=True)
class GateCheck:
    code: str
    status: str
    message: str
    object_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: str
    checks: tuple[GateCheck, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status,
            "checks": [asdict(check) for check in self.checks],
        }
```

Implement stable Design Gate checks:

```text
DESIGN_PRIMARY_QUESTION_PRESENT
DESIGN_SCOPE_INCLUDED_PRESENT
DESIGN_SCOPE_EXCLUDED_PRESENT
DESIGN_ROUTER_COMPLETE
DESIGN_QUESTION_TREE_VALID
DESIGN_REQUIRED_QUESTIONS_COVERED
DESIGN_CRITICAL_CLAIMS_HAVE_COUNTER
DESIGN_VALIDATION_PLAN_PRESENT
DESIGN_INVALIDATION_PLAN_PRESENT
DESIGN_REFERENCES_AUDITABLE
DESIGN_PROVENANCE_COMPLETE
DESIGN_NO_PREMATURE_CONCLUSIONS
```

Gate aggregation rules:

- any failed required check → `fail`;
- no failures and at least one warning → `pass_with_warnings`;
- all applicable checks pass → `pass`;
- gate does not apply to the creation stage → `not_applicable`.

- [ ] **Step 4: Run gate tests**

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/research_project_v2/gates.py \
  tests/test_research_project_v2_gates.py
rtk git commit -m "feat: add staged research quality gates"
```

## Task 7: Stable-ID Version Diff

**Files:**

- Create: `src/stock_research/research_project_v2/diff.py`
- Test: `tests/test_research_project_v2_diff.py`

- [ ] **Step 1: Write failing diff tests**

Build two version fixtures with stable IDs. Add one claim only to the second version and assert `added`; change an existing claim lifecycle to `removed_from_scope`; change only `claim_status` and assert `status_changed`; change `claim_text` with the same ID and assert `modified`; create `claim:new` with `supersedes_claim_id=claim:old` and assert `superseded`; leave one question identical and assert `unchanged`; finally change `project_id` and parent ancestry separately and assert `RESEARCH_PROJECT_DIFF_PROJECT_MISMATCH` and `RESEARCH_PROJECT_DIFF_ANCESTRY_INVALID`.

Use two complete version fixtures and assert exact object-family output.

- [ ] **Step 2: Verify tests fail**

- [ ] **Step 3: Implement diff**

```python
OBJECT_FAMILIES = {
    "questions": "question_id",
    "question_tree_nodes": "tree_node_id",
    "claims": "claim_id",
    "claim_relations": "relation_id",
    "evidence_requirements": "requirement_id",
    "evidence_assessments": "assessment_id",
    "causal_nodes": "causal_node_id",
    "causal_edges": "causal_edge_id",
    "validation_metrics": "metric_id",
    "invalidation_conditions": "condition_id",
    "references": "reference_id",
    "company_capture_assessments": "assessment_id",
}


def diff_versions(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before["project_id"] != after["project_id"]:
        raise ResearchProjectV2Error(
            "versions belong to different projects",
            code="RESEARCH_PROJECT_DIFF_PROJECT_MISMATCH",
        )
    changes = {}
    for family, id_field in OBJECT_FAMILIES.items():
        before_rows = {row[id_field]: row for row in before["snapshot"][family]}
        after_rows = {row[id_field]: row for row in after["snapshot"][family]}
        changes[family] = classify_family_changes(
            family,
            id_field,
            before_rows,
            after_rows,
        )
    return {
        "project_id": before["project_id"],
        "from_version": before["semantic_version"],
        "to_version": after["semantic_version"],
        "from_content_hash": before["content_hash"],
        "to_content_hash": after["content_hash"],
        "changes": changes,
    }
```

Compare status fields separately from content fields. Never use fuzzy text similarity. Include `from_content_hash` and `to_content_hash` in output.

- [ ] **Step 4: Run diff tests**

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/research_project_v2/diff.py \
  tests/test_research_project_v2_diff.py
rtk git commit -m "feat: diff immutable research project versions"
```

## Task 8: Summary, CLI, And Root Command Wiring

**Files:**

- Create: `src/stock_research/research_project_v2/summary.py`
- Create: `src/stock_research/research_project_v2/cli.py`
- Modify: `src/stock_research/research_project_v2/__init__.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_research_project_v2_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create seven tests with exact assertions: `list` returns four sorted project rows and exit 0; `show --project demo` returns the version pointed to by `current_version`; invalid schema fixture exits 2; drift audit exits 3; failed Design Gate exits 4; invalid diff ancestry exits 7; and root CLI passes the remaining arguments unchanged to `run_research_project_v2_cli`.

Invoke `cli([...], layout=test_layout)` directly in focused tests. Root CLI test invokes `main_for_args(["research-project-v2", "list"])` with the delegated function monkeypatched.

- [ ] **Step 2: Verify tests fail**

- [ ] **Step 3: Implement deterministic summaries**

```python
def summarize_version(version: dict[str, Any]) -> dict[str, Any]:
    snapshot = version["snapshot"]
    return {
        "project_id": version["project_id"],
        "version_id": version["version_id"],
        "semantic_version": version["semantic_version"],
        "creation_stage": version["creation_stage"],
        "project_stage": snapshot["project_stage"],
        "evidence_stage": snapshot["evidence_stage"],
        "conclusion_status": snapshot["conclusion_status"],
        "investment_status": snapshot["investment_status"],
        "question_count": len(snapshot["questions"]),
        "claim_count": len(snapshot["claims"]),
        "requirement_count": len(snapshot["evidence_requirements"]),
        "assessment_count": len(snapshot["evidence_assessments"]),
    }
```

- [ ] **Step 4: Implement CLI and exit codes**

```python
EXIT_SUCCESS = 0
EXIT_VALIDATION = 2
EXIT_REFERENCE = 3
EXIT_GATE = 4
EXIT_IMMUTABILITY = 5
EXIT_NOT_FOUND = 6
EXIT_DIFF = 7
EXIT_RUNTIME = 10
```

All commands print JSON with `ensure_ascii=False` and deterministic key ordering. `pass_with_warnings` returns 0. Domain errors map by code family; unexpected exceptions return 10 and a stable `RESEARCH_PROJECT_RUNTIME_ERROR` envelope.

Register the root command in `src/stock_research/cli.py`:

```python
if raw_argv and raw_argv[0] == "research-project-v2":
    return run_research_project_v2_cli(raw_argv[1:])
```

Also add the import near the existing Theme Research CLI imports.

- [ ] **Step 5: Run CLI tests**

- [ ] **Step 6: Run help smoke**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.cli research-project-v2 --help
```

Expected: list, show, validate, summary, audit-references, diff, and gate appear.

- [ ] **Step 7: Commit**

```bash
rtk git add src/stock_research/research_project_v2 \
  src/stock_research/cli.py tests/test_research_project_v2_cli.py
rtk git commit -m "feat: expose research project v2 cli"
```

## Task 9: Four Research-Design Pilots, Fixtures, And Rebuildable Index

**Files:**

- Create: `artifacts/research_projects/v2/projects/ai_compute_pcb_value_migration/**`
- Create: `artifacts/research_projects/v2/projects/humanoid_robot_scale_up_bottlenecks/**`
- Create: `artifacts/research_projects/v2/projects/new_energy_storage_route_competition/**`
- Create: `artifacts/research_projects/v2/projects/high_end_medical_device_commercialization/**`
- Create: `artifacts/research_projects/v2/index/research_project_index_v2.json`
- Create: `artifacts/research_projects/v2/fixtures/valid/**`
- Create: `artifacts/research_projects/v2/fixtures/invalid/**`
- Test: `tests/test_research_project_v2_pilots.py`

- [ ] **Step 1: Write failing pilot tests**

```python
PILOT_SLUGS = {
    "ai_compute_pcb_value_migration",
    "humanoid_robot_scale_up_bottlenecks",
    "new_energy_storage_route_competition",
    "high_end_medical_device_commercialization",
}


def test_exactly_four_r1_pilots_exist():
    assert set(list_project_slugs()) == PILOT_SLUGS


@pytest.mark.parametrize("project_slug", sorted(PILOT_SLUGS))
def test_pilot_is_design_only_and_passes_design_gate(project_slug):
    version = load_version(project_slug)
    result = evaluate_gate(version, gate="design")

    assert version["creation_stage"] == "research_design"
    assert version["snapshot"]["project_stage"] == "research_ready"
    assert version["snapshot"]["evidence_stage"] == "requirements_defined"
    assert version["snapshot"]["conclusion_status"] == "unavailable"
    assert version["snapshot"]["investment_status"] == "not_assessed"
    assert version["snapshot"]["evidence_assessments"] == []
    assert version["snapshot"]["company_capture_assessments"] == []
    assert result.status in {"pass", "pass_with_warnings"}
```

Also assert the expected Router methods and primary question for each pilot.

- [ ] **Step 2: Verify tests fail because pilots do not exist**

- [ ] **Step 3: Create each project identity and immutable v0.1.0 snapshot**

Every snapshot must contain:

- one exact primary question from the approved spec;
- included and excluded scope;
- Router primary/secondary methods with reasons;
- required and excluded modules;
- at least six questions covering mechanism, constraint, economics, company capture, counterfactual, and validation;
- at least one primary hypothesis and one counter or alternative hypothesis;
- claim relations;
- evidence requirements for every required question and critical claim;
- causal nodes/edges marked as hypotheses, not conclusions;
- typed validation metrics without observed results;
- typed invalidation conditions without triggered status;
- background or scope references to existing V1/Industry Catalog objects where available;
- no Evidence Assessment;
- no company-capture assessment;
- no supported claim;
- no publication conclusion;
- no buy/sell language.

Project-specific Router requirements:

```text
AI PCB:
  primary system_architecture
  secondary manufacturing_process

Humanoid robots:
  primary complex_system
  secondary engineering_scale_up

New energy storage:
  primary technology_route
  secondary infrastructure_economics

High-end medical devices:
  primary lifecycle
  secondary regulation, system_architecture
```

- [ ] **Step 4: Calculate hashes and write manifests**

Use the package function rather than manual hashing:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m \
  stock_research.research_project_v2.cli rebuild-index --write
```

Add `rebuild-index --write` as a maintainer-only subcommand. It calculates missing version hashes, appends new manifest rows, rejects an existing version whose manifest hash differs, and rewrites only `index/research_project_index_v2.json`. It must not edit an already-manifested version file.

- [ ] **Step 5: Add valid and invalid fixtures**

Invalid fixtures must cover:

```text
question dependency cycle
duplicate claim ID
missing reference
hash mismatch
premature supported claim
evidence assessment in research_design
company capture in research_design
unmarked causal cycle
invalid version manifest
```

- [ ] **Step 6: Run pilot and full V2 tests**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_*.py -q
```

Expected: all V2 tests pass.

- [ ] **Step 7: Run CLI acceptance**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.cli research-project-v2 list
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.cli research-project-v2 validate --all
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.cli research-project-v2 gate \
  --project ai_compute_pcb_value_migration --version 0.1.0 --gate design
```

Expected: four projects, validation success, Design Gate pass or pass_with_warnings.

- [ ] **Step 8: Commit**

```bash
rtk git add artifacts/research_projects/v2 \
  tests/test_research_project_v2_pilots.py
rtk git commit -m "data: seed research project v2 design pilots"
```

## Task 10: Documentation, Scope Guard, And Final Verification

**Files:**

- Create: `docs/research_operating_layer_v2_r1.md`
- Modify: `docs/research_operating_layer_v2_goal_and_roadmap.md`
- Create: `tests/test_research_project_v2_scope_guard.py`

- [ ] **Step 1: Write the failing scope-guard test**

```python
from pathlib import Path


def test_r1_does_not_modify_v1_api_dashboard_or_database_contracts():
    forbidden = {
        "src/stock_research/dashboard/app.py",
        "src/stock_research/theme_research_db_schema.py",
        "dashboard/src/components/ThemeResearchWorkspace.tsx",
    }
    changed = {
        line.strip()
        for line in Path("/private/tmp/research_project_v2_changed_files.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    assert forbidden.isdisjoint(changed)
    assert not any(path.startswith("artifacts/theme_decomposition/") for path in changed)
    assert not any(path.startswith("artifacts/technology_industry_catalog/") for path in changed)
```

Generate the changed-file list before running this test:

```bash
rtk git diff --name-only 5548068..HEAD > /private/tmp/research_project_v2_changed_files.txt
```

- [ ] **Step 2: Write the R1 operator documentation**

Create these exact documentation sections: `Purpose`, `Artifact Layout`, `Project Identity`, `Immutable Versions`, `Event Stream`, `Version Manifest`, `CLI Commands`, `Exit Codes`, `Research Design Gate`, `Reference Drift`, `Adding A Design Project`, `R1 Non-goals`, and `Production Migration Prohibition`. Include a complete command example for each CLI subcommand and a checklist that forbids supported claims, evidence assessments, company-capture conclusions, published conclusions, and investment judgments in a design project.

Update the roadmap to mark R1 complete only after all verification commands pass.

- [ ] **Step 3: Run focused backend tests**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_*.py -q
```

Expected: all V2 tests pass with zero failures.

- [ ] **Step 4: Run regression tests for referenced V1 systems**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_theme_decomposition.py \
  tests/test_theme_company_mapping.py \
  tests/test_technology_industry_catalog.py \
  tests/test_dashboard_theme_research.py -q
```

Expected: all selected V1 tests pass.

- [ ] **Step 5: Verify no frontend or database implementation changed**

```bash
rtk git diff --name-only 5548068..HEAD
```

Expected: no `dashboard/`, `src/stock_research/dashboard/`, Theme Research DB schema, V1 theme artifact, or Industry Catalog artifact files.

- [ ] **Step 6: Run CLI smoke matrix**

Run list, show, validate --all, summary, audit-references, diff against a fixture version pair, and Design Gate. Record the exact exit codes. Expected: normal commands return 0; invalid fixtures return their designed 2/3/4/5/7 codes.

- [ ] **Step 7: Commit**

```bash
rtk git add docs/research_operating_layer_v2_r1.md \
  docs/research_operating_layer_v2_goal_and_roadmap.md \
  tests/test_research_project_v2_scope_guard.py
rtk git commit -m "docs: complete research operating layer v2 r1"
```

## Final Acceptance Checklist

- [ ] Four project identities and four immutable v0.1.0 versions exist.
- [ ] All four projects pass Research Design Gate only.
- [ ] No pilot has supported claims, evidence assessments, company-capture conclusions, published conclusions, or investment judgments.
- [ ] Schema, semantic, hash, manifest, event, reference, gate, diff, and CLI tests pass.
- [ ] V1 Theme Research and Technology Industry Catalog regression tests pass.
- [ ] No production migration was added or executed.
- [ ] No Theme Research API or Dashboard behavior changed.
- [ ] No file under the 27 V1 themes or Industry Catalog was modified.
- [ ] The final changed-file scope matches the R1 boundary.
