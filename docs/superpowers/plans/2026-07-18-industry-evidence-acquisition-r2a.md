# Industry Evidence Acquisition R2A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the additive `v2_1` Industry Research evidence-acquisition baseline without modifying R1 artifacts, V1 knowledge assets, production databases, APIs, Dashboard behavior, or introducing company/stock evaluation.

**Architecture:** Add an isolated `artifacts/research_projects/v2_1` generation and a focused `stock_research.research_project_v2_1` package. R2A reuses R1 canonical hashing and common semantic rules through projections, while adding first-class `research_layer=industry_research`, immutable upstream R1 references, Search Plans, source discovery, secure snapshots, document normalization, industry Evidence Assessment, source-independence/freshness/conflict checks, and an Industry Design Gate.

**Tech Stack:** Python 3.11+, JSON Schema Draft 2020-12, `jsonschema`, RFC 8785/SHA-256, `requests`, `pypdf`, standard-library HTML/CSV/JSON parsers, pytest, repository JSON/JSONL artifacts.

---

## Scope Boundaries

This plan must not:

- modify any file under `artifacts/research_projects/v2/`;
- modify any file under `artifacts/theme_decomposition/`;
- modify any file under `artifacts/technology_industry_catalog/`;
- modify `src/stock_research/dashboard/` or `dashboard/`;
- execute or add a production database migration;
- add a production API route or Research Workbench UI;
- discover candidate companies, create company capability stages, or rate companies;
- read stock prices, valuations, trading signals, or produce a stock rating;
- automatically promote a claim or bottleneck because a document was downloaded or parsed.

R2A may use company disclosures only as industry engineering, capacity, qualification, or supply evidence. It may not create `company_capture` or `stock_evaluation` artifacts.

## File Structure

Create the isolated package:

```text
src/stock_research/research_project_v2_1/
├── __init__.py             public R2A read/validate API
├── layout.py               v2_1 repository paths
├── schema.py               schema dispatch and validation
├── loader.py               layered identity/version/index/manifest loading
├── semantic.py             layer, upstream-reference and Search Plan semantics
├── search_plan.py          requirement-to-query plan compilation
├── discovery.py            imported/direct discovery normalization and deduplication
├── snapshot.py             secure fetching and content-addressed raw snapshots
├── parsers.py              HTML, PDF, CSV and JSON parsing
├── normalize.py            normalized document and locator construction
├── evidence.py             independence, freshness, conflict and assessment logic
├── gates.py                Industry Design Gate
├── maintenance.py          safe transactional v2_1 index/manifest rebuild
└── cli.py                  R2A commands and exit-code mapping
```

Create the additive artifact root:

```text
artifacts/research_projects/v2_1/
├── schema/
├── projects/
├── evidence/
│   ├── discovery/
│   ├── raw/
│   ├── metadata/
│   ├── normalized/
│   └── assessments/
├── index/research_project_index_v2_1.json
└── fixtures/
    ├── discovery/
    ├── documents/
    ├── valid/
    └── invalid/
```

Tests:

```text
tests/test_research_project_v2_1_layout.py
tests/test_research_project_v2_1_schema.py
tests/test_research_project_v2_1_loader.py
tests/test_research_project_v2_1_search_plan.py
tests/test_research_project_v2_1_discovery.py
tests/test_research_project_v2_1_snapshot.py
tests/test_research_project_v2_1_parsers.py
tests/test_research_project_v2_1_evidence.py
tests/test_research_project_v2_1_gates.py
tests/test_research_project_v2_1_pilots.py
tests/test_research_project_v2_1_cli.py
tests/test_research_project_v2_1_scope_guard.py
```

## Task 1: Isolated Package, Layout, And R1 Freeze Guard

**Files:**

- Create: `src/stock_research/research_project_v2_1/__init__.py`
- Create: `src/stock_research/research_project_v2_1/layout.py`
- Create: `tests/test_research_project_v2_1_layout.py`
- Create: `tests/test_research_project_v2_1_scope_guard.py`

- [ ] **Step 1: Write the failing layout tests**

```python
from stock_research.research_project_v2.layout import ResearchProjectLayout
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


def test_v2_1_layout_is_isolated_from_r1():
    r1 = ResearchProjectLayout.default()
    layered = LayeredResearchLayout.default()

    assert layered.root.name == "v2_1"
    assert layered.root != r1.root
    assert layered.projects_dir == layered.root / "projects"
    assert layered.evidence_discovery_dir == layered.root / "evidence/discovery"
    assert layered.evidence_raw_dir == layered.root / "evidence/raw"
    assert layered.evidence_metadata_dir == layered.root / "evidence/metadata"
    assert layered.evidence_normalized_dir == layered.root / "evidence/normalized"
    assert layered.evidence_assessments_dir == layered.root / "evidence/assessments"
    assert layered.index_path == layered.root / "index/research_project_index_v2_1.json"
```

Add a scope test that rejects changes under R1/V1/UI/database paths and explicitly permits only `v2_1`, the new package, its tests, the root CLI delegation, and R2A documentation.

- [ ] **Step 2: Run the tests and confirm the package is missing**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_layout.py -q
```

Expected: collection fails with `ModuleNotFoundError: stock_research.research_project_v2_1`.

- [ ] **Step 3: Implement the frozen layout**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class LayeredResearchLayout:
    root: Path

    @classmethod
    def default(cls) -> "LayeredResearchLayout":
        return cls(REPOSITORY_ROOT / "artifacts/research_projects/v2_1")

    @property
    def schema_dir(self) -> Path:
        return self.root / "schema"

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def evidence_raw_dir(self) -> Path:
        return self.root / "evidence/raw"

    @property
    def evidence_discovery_dir(self) -> Path:
        return self.root / "evidence/discovery"

    @property
    def evidence_metadata_dir(self) -> Path:
        return self.root / "evidence/metadata"

    @property
    def evidence_normalized_dir(self) -> Path:
        return self.root / "evidence/normalized"

    @property
    def evidence_assessments_dir(self) -> Path:
        return self.root / "evidence/assessments"

    @property
    def index_path(self) -> Path:
        return self.root / "index/research_project_index_v2_1.json"

    def project_dir(self, project_slug: str) -> Path:
        return self.projects_dir / project_slug
```

Export only `LayeredResearchLayout` initially.

- [ ] **Step 4: Run layout and existing R1 storage tests**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_layout.py \
  tests/test_research_project_v2_storage.py \
  tests/test_research_project_v2_pilots.py -q
```

Expected: all tests pass and the R1 pilot set remains exactly four.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/research_project_v2_1 \
  tests/test_research_project_v2_1_layout.py \
  tests/test_research_project_v2_1_scope_guard.py
rtk git commit -m "feat: scaffold layered research v2.1 package"
```

## Task 2: V2.1 Schemas And Layered Schema Registry

**Files:**

- Create: `artifacts/research_projects/v2_1/schema/definitions_v2_1.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/research_project_identity_v2_1.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/industry_research_version_v2_1.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/search_plan_v2_1.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/evidence_artifact_v2_1.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/normalized_document_v2_1.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/industry_evidence_assessment_v2_1.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/research_project_index_v2_1.schema.json`
- Create: `src/stock_research/research_project_v2_1/schema.py`
- Create: `tests/test_research_project_v2_1_schema.py`

- [ ] **Step 1: Write failing schema tests**

Test these exact contracts:

```python
def test_identity_requires_first_class_industry_layer(sample_layered_identity):
    validate_v2_1_schema_payload("research_project_identity_v2_1", sample_layered_identity)


def test_identity_rejects_company_layer_in_r2a(sample_layered_identity):
    broken = deepcopy(sample_layered_identity)
    broken["research_layer"] = "company_capture"
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload("research_project_identity_v2_1", broken)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"


def test_industry_version_rejects_company_and_stock_objects(sample_industry_version):
    broken = deepcopy(sample_industry_version)
    broken["snapshot"]["company_capability_assessments"] = []
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_research_version_v2_1", broken)
```

Also test that R1 `2.0.0` payloads are rejected by the v2.1 registry rather than silently reinterpreted.

- [ ] **Step 2: Define common v2.1 fields**

`definitions_v2_1.schema.json` must define:

```text
research_layer: industry_research | company_capture | stock_evaluation
evidence_channel: industry | company | market
upstream_research_ref
search_query
search_plan
source_candidate
source_relationship
evidence_artifact
normalized_section
normalized_document
industry_evidence_assessment
freshness_assessment
conflict_summary
```

For R2A, the identity schema must constrain `research_layer` to `industry_research` even though the common enum contains all three future layers.

`upstream_research_ref` requires:

```json
{
  "upstream_research_ref_id": "string",
  "upstream_research_layer": ["industry_research", "company_capture", "stock_evaluation", null],
  "upstream_project_id": "string",
  "upstream_version_id": "string",
  "upstream_object_type": "string",
  "upstream_object_id": ["string", null],
  "upstream_gate_result_id": ["string", null],
  "upstream_content_hash": "64 lowercase hex characters",
  "referenced_at": "RFC3339 date-time",
  "scope_note": "non-empty string"
}
```

- [ ] **Step 3: Define the Industry Research snapshot**

The version schema keeps the R1 common snapshot collections and adds only these R2A collections:

```text
research_layer
upstream_research_refs
search_plans
source_candidates
source_relationships
evidence_artifacts
normalized_documents
industry_evidence_assessments
conflict_summaries
```

It must not contain these keys:

```text
candidate_companies
company_capability_assessments
company_ratings
stock_ratings
valuation_assessments
watchlist_candidates
strategy_hypotheses
```

Because every object uses `additionalProperties: false`, adding any forbidden key fails schema validation.

- [ ] **Step 4: Implement schema dispatch**

```python
SCHEMA_FILES = {
    "research_project_identity_v2_1": "research_project_identity_v2_1.schema.json",
    "industry_research_version_v2_1": "industry_research_version_v2_1.schema.json",
    "search_plan_v2_1": "search_plan_v2_1.schema.json",
    "evidence_artifact_v2_1": "evidence_artifact_v2_1.schema.json",
    "normalized_document_v2_1": "normalized_document_v2_1.schema.json",
    "industry_evidence_assessment_v2_1": "industry_evidence_assessment_v2_1.schema.json",
    "research_project_index_v2_1": "research_project_index_v2_1.schema.json",
}


def validate_v2_1_schema_payload(
    schema_name: str,
    payload: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
) -> None:
    selected_layout = layout or LayeredResearchLayout.default()
    try:
        filename = SCHEMA_FILES[schema_name]
    except KeyError as exc:
        raise ResearchProjectV2Error(
            f"Unknown v2.1 schema: {schema_name}",
            code="RESEARCH_PROJECT_V2_1_SCHEMA_NOT_FOUND",
            details={"schema": schema_name},
        ) from exc
    schema = json.loads((selected_layout.schema_dir / filename).read_text(encoding="utf-8"))
    definitions = json.loads(
        (selected_layout.schema_dir / "definitions_v2_1.schema.json").read_text(encoding="utf-8")
    )
    resolver = RefResolver.from_schema(
        schema,
        store={"definitions_v2_1.schema.json": definitions},
    )
    errors = sorted(
        Draft202012Validator(
            schema,
            resolver=resolver,
            format_checker=FormatChecker(),
        ).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        first = errors[0]
        raise ResearchProjectV2Error(
            first.message,
            code="RESEARCH_PROJECT_V2_1_SCHEMA_INVALID",
            details={
                "schema": schema_name,
                "path": list(first.absolute_path),
            },
        )
```

Unknown schema names raise `RESEARCH_PROJECT_V2_1_SCHEMA_NOT_FOUND`; validation failures raise `RESEARCH_PROJECT_V2_1_SCHEMA_INVALID` with deterministic `path` and `schema` details.

- [ ] **Step 5: Run schema tests**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_schema.py -q
```

Expected: all schema tests and `Draft202012Validator.check_schema` checks pass.

- [ ] **Step 6: Commit**

```bash
rtk git add artifacts/research_projects/v2_1/schema \
  src/stock_research/research_project_v2_1/schema.py \
  tests/test_research_project_v2_1_schema.py
rtk git commit -m "feat: define layered industry research schemas"
```

## Task 3: Layered Loader, Immutable Versions, And Upstream R1 References

**Files:**

- Create: `src/stock_research/research_project_v2_1/loader.py`
- Create: `src/stock_research/research_project_v2_1/semantic.py`
- Create: `tests/test_research_project_v2_1_loader.py`

- [ ] **Step 1: Write failing loader tests**

Cover:

- sorted layered project discovery;
- identity and current-version loading;
- v2.1 content hash and manifest verification;
- R1 and v2.1 roots never cross-scan;
- an upstream R1 reference resolves by `project_id + version_id + content_hash`;
- a missing or changed upstream version returns `RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID`;
- an R1 reference with `upstream_research_layer != null` is rejected;
- duplicate upstream references are rejected;
- company/stock layers are rejected by R2A semantics.

- [ ] **Step 2: Implement immutable v2.1 loading**

Public signatures:

```python
def list_layered_project_slugs(
    *, layout: LayeredResearchLayout | None = None
) -> list[str]:
    selected = layout or LayeredResearchLayout.default()
    if not selected.projects_dir.is_dir():
        return []
    return sorted(
        entry.name
        for entry in selected.projects_dir.iterdir()
        if _is_safe_project_dir(entry, selected)
    )


def load_layered_project(
    project_slug: str,
    *, layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    selected = layout or LayeredResearchLayout.default()
    path = _identity_path(project_slug, selected)
    payload = _read_json_object(path)
    validate_v2_1_schema_payload(
        "research_project_identity_v2_1", payload, layout=selected
    )
    return payload


def list_layered_versions(
    project_slug: str,
    *, layout: LayeredResearchLayout | None = None,
) -> list[str]:
    selected = layout or LayeredResearchLayout.default()
    load_layered_project(project_slug, layout=selected)
    versions_dir = _versions_dir(project_slug, selected)
    return sorted(_discover_semantic_versions(versions_dir), key=_semver_key)


def load_industry_version(
    project_slug: str,
    semantic_version: str | None = None,
    *, layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    selected = layout or LayeredResearchLayout.default()
    identity = load_layered_project(project_slug, layout=selected)
    version = semantic_version or identity["current_version"].rsplit(":", 1)[-1]
    payload = _read_json_object(_version_path(project_slug, version, selected))
    validate_v2_1_schema_payload(
        "industry_research_version_v2_1", payload, layout=selected
    )
    _verify_manifest_and_hash(identity, payload, version, selected)
    validate_industry_version_semantics(payload)
    return payload


def load_layered_index(
    *, layout: LayeredResearchLayout | None = None
) -> dict[str, Any]:
    selected = layout or LayeredResearchLayout.default()
    payload = _read_json_object(selected.index_path)
    validate_v2_1_schema_payload(
        "research_project_index_v2_1", payload, layout=selected
    )
    return payload
```

Implement `_is_safe_project_dir`, `_identity_path`, `_versions_dir`, `_discover_semantic_versions`, `_semver_key`, `_version_path`, `_read_json_object`, and `_verify_manifest_and_hash` in this task. Use R1 `content_sha256`, the exact R1 slug/SemVer regexes, managed-path containment, symlink rejection, exact manifest row matching, and the same exit-family semantics as R1 with `V2_1` error codes.

- [ ] **Step 3: Implement upstream R1 resolution**

```python
def resolve_upstream_r1_version(reference: dict[str, Any]) -> dict[str, Any]:
    index = load_index()
    matches = [row for row in index["projects"] if row["project_id"] == reference["upstream_project_id"]]
    if len(matches) != 1:
        raise upstream_error(reference, "project_id did not resolve uniquely")
    project_slug = matches[0]["project_slug"]
    semantic_version = reference["upstream_version_id"].rsplit(":", 1)[-1]
    version = load_version(project_slug, semantic_version)
    if version["version_id"] != reference["upstream_version_id"]:
        raise upstream_error(reference, "version_id mismatch")
    if version["content_hash"] != reference["upstream_content_hash"]:
        raise upstream_error(reference, "content_hash mismatch")
    return version
```

The function is read-only and never promotes the R1 project to an Industry layer.

- [ ] **Step 4: Reuse R1 common semantics by projection**

```python
R2A_SNAPSHOT_FIELDS = {
    "research_layer",
    "upstream_research_refs",
    "search_plans",
    "source_candidates",
    "source_relationships",
    "evidence_artifacts",
    "normalized_documents",
    "industry_evidence_assessments",
    "conflict_summaries",
}


def common_r1_projection(version: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(version)
    projected["artifact_version"] = "2.0.0"
    projected["snapshot"] = {
        key: value
        for key, value in version["snapshot"].items()
        if key not in R2A_SNAPSHOT_FIELDS
    }
    return projected
```

`validate_industry_version_semantics` first runs R1 common semantics on the projection, then validates layer/upstream/Search Plan/evidence object relationships. It must not run R1 schema validation on the projection.

- [ ] **Step 5: Run loader and R1 regression tests**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_loader.py \
  tests/test_research_project_v2_storage.py \
  tests/test_research_project_v2_references.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/stock_research/research_project_v2_1/loader.py \
  src/stock_research/research_project_v2_1/semantic.py \
  tests/test_research_project_v2_1_loader.py
rtk git commit -m "feat: load layered industry research versions"
```

## Task 4: Evidence Requirements And Search Plans

**Files:**

- Create: `src/stock_research/research_project_v2_1/search_plan.py`
- Create: `tests/test_research_project_v2_1_search_plan.py`

- [ ] **Step 1: Write failing Search Plan tests**

Use an Industry Evidence Requirement with target claim `claim:industry:primary`. Assert that the compiled plan contains separate query groups for mechanism, quantitative validation, counter-evidence, and primary/engineering sources.

```python
def test_compile_search_plan_separates_support_and_counter_queries(requirement):
    plan = compile_search_plan(
        requirement,
        project_id="research_project:industry-demo",
        version_id="research_version:industry-demo:0.1.0",
        domain_terms=["high-layer PCB", "low-loss laminate"],
    )

    assert plan["evidence_channel"] == "industry"
    assert {query["query_role"] for query in plan["queries"]} == {
        "mechanism",
        "quantification",
        "counter_evidence",
        "primary_engineering",
    }
    assert plan["stop_conditions"]
```

Also test missing counter search, empty source classes, duplicate query IDs, stock terms, and company-ranking terms.

- [ ] **Step 2: Implement the deterministic compiler**

```python
FORBIDDEN_INDUSTRY_SEARCH_TERMS = {
    "目标价", "买入", "卖出", "股票推荐", "估值最低", "最强龙头",
    "target price", "buy rating", "sell rating", "top stock",
}


def compile_search_plan(
    requirement: dict[str, Any],
    *,
    project_id: str,
    version_id: str,
    domain_terms: list[str],
) -> dict[str, Any]:
    question = requirement["question_to_resolve"].strip()
    terms = " ".join(term.strip() for term in domain_terms if term.strip())
    if not question or not terms:
        raise ResearchProjectV2Error(
            "Search Plan requires a question and domain terms",
            code="RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID",
            details={"requirement_id": requirement["requirement_id"]},
        )
    query_specs = (
        ("mechanism", f"{terms} {question} mechanism engineering"),
        ("quantification", f"{terms} {question} capacity yield price data"),
        ("counter_evidence", f"{terms} {question} alternative substitution limitation"),
        ("primary_engineering", f"{terms} standard specification technical document"),
    )
    queries = [
        {
            "query_id": f"query:{requirement['requirement_id']}:{role}",
            "query_role": role,
            "query_text": text,
            "required_terms": domain_terms,
            "excluded_terms": sorted(FORBIDDEN_INDUSTRY_SEARCH_TERMS),
            "source_classes": requirement["required_source_classes"],
            "priority": index,
        }
        for index, (role, text) in enumerate(query_specs, start=1)
    ]
    return {
        "search_plan_id": f"search_plan:{requirement['requirement_id']}",
        "project_id": project_id,
        "version_id": version_id,
        "evidence_channel": "industry",
        "requirement_ids": [requirement["requirement_id"]],
        "queries": queries,
        "languages": ["zh-CN", "en"],
        "geography": ["CN", "global"],
        "publication_window": requirement["required_freshness"],
        "result_limit_per_query": 20,
        "deduplication_policy": "normalized_url_then_content_hash",
        "stop_conditions": [
            "all query roles executed",
            "minimum source-class coverage reached",
            "counter-evidence query executed",
        ],
        "status": "planned",
        "provenance": requirement["provenance"],
    }
```

The plan must record exact requirement IDs, source-class targets, languages, geography, publication window, query roles, result limits, deduplication policy, and stop conditions. It must not infer a company list.

- [ ] **Step 3: Implement Search Plan semantic validation**

Require:

- every required Industry Evidence Requirement is covered by at least one Search Plan;
- every plan has a counter-evidence query;
- every plan targets at least two source classes unless the requirement explicitly requires one named primary standard;
- query IDs are globally unique;
- every query is non-empty and free of forbidden investment terms;
- `status` is `planned`, `active`, `complete`, `superseded`, or `cancelled`.

- [ ] **Step 4: Run tests and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_search_plan.py -q
rtk git add src/stock_research/research_project_v2_1/search_plan.py \
  tests/test_research_project_v2_1_search_plan.py
rtk git commit -m "feat: add industry evidence search plans"
```

## Task 5: Source Discovery Normalization And Deduplication

**Files:**

- Create: `src/stock_research/research_project_v2_1/discovery.py`
- Create: `artifacts/research_projects/v2_1/fixtures/discovery/imported_results.json`
- Create: `tests/test_research_project_v2_1_discovery.py`

- [ ] **Step 1: Write failing discovery tests**

Fixtures must contain duplicate URLs with fragments, reordered query strings, tracking parameters, one direct PDF, one standards page, one company engineering document, and one stock-opinion page.

Assert:

- URL fragments and `utm_*`, `spm`, `from`, `ref` parameters are removed;
- remaining query pairs are sorted;
- host names are lowercase and IDNA-normalized;
- duplicates collapse deterministically;
- unsupported schemes and credential-bearing URLs are rejected;
- stock-opinion results are marked `excluded_by_policy` rather than becoming candidates;
- ordering is `priority`, then `normalized_url`, then `candidate_id`.

- [ ] **Step 2: Define provider and result contracts**

```python
@dataclass(frozen=True)
class DiscoveryResult:
    url: str
    title: str
    snippet: str
    publisher: str | None
    publish_date: str | None
    source_class: str
    query_id: str
    rank: int


class DiscoveryProvider(Protocol):
    def search(self, query: dict[str, Any]) -> list[DiscoveryResult]:
        raise NotImplementedError
```

Implement `ImportedJsonDiscoveryProvider` and `DirectUrlDiscoveryProvider`. Live search-engine credentials are not added in R2A; production providers can implement the protocol later without changing artifact contracts.

- [ ] **Step 3: Implement URL normalization and candidate IDs**

```python
TRACKING_QUERY_KEYS = {"spm", "from", "ref", "source"}


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ResearchProjectV2Error(
            "Discovery URL must use http or https",
            code="RESEARCH_PROJECT_V2_1_DISCOVERY_URL_INVALID",
            details={"url": url},
        )
    if parsed.username or parsed.password:
        raise ResearchProjectV2Error(
            "Credential-bearing discovery URL is forbidden",
            code="RESEARCH_PROJECT_V2_1_DISCOVERY_URL_INVALID",
            details={"url": url},
        )
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    port = f":{parsed.port}" if parsed.port else ""
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_QUERY_KEYS
    ]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            f"{host}{port}",
            parsed.path or "/",
            urllib.parse.urlencode(sorted(query)),
            "",
        )
    )


def source_candidate_id(normalized_url: str, title: str) -> str:
    digest = hashlib.sha256(f"{normalized_url}\n{title.strip()}".encode()).hexdigest()
    return f"source_candidate:{digest[:24]}"
```

Candidate payloads include discovery query, rank, source class, normalized URL, title, publisher, publish date, exclusion status, dedup key, and provenance.

`write_discovery_batch` stores one immutable batch at:

```text
evidence/discovery/<search_plan_id>/<batch_content_sha256>.json
```

The batch contains the Search Plan ID, executed query IDs, provider name, discovery timestamp, included candidates, policy-excluded results, and a top-level content hash. Re-running the same imported results must reuse identical bytes and must not overwrite a different payload at the same path.

- [ ] **Step 4: Run tests and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_discovery.py -q
rtk git add src/stock_research/research_project_v2_1/discovery.py \
  artifacts/research_projects/v2_1/fixtures/discovery/imported_results.json \
  tests/test_research_project_v2_1_discovery.py
rtk git commit -m "feat: normalize industry source discovery"
```

## Task 6: Secure Fetching And Content-Addressed Snapshots

**Files:**

- Create: `src/stock_research/research_project_v2_1/snapshot.py`
- Create: `tests/test_research_project_v2_1_snapshot.py`

- [ ] **Step 1: Write failing snapshot security tests**

Use an injected fake transport. Test:

- only `http` and `https` schemes;
- user-info URLs are rejected;
- loopback, link-local, private, multicast and unspecified IPs are rejected by default;
- every redirect target is revalidated;
- redirect count is at most five;
- response size is capped at 25 MiB using streamed chunks;
- accepted media types are PDF, HTML, plain text, JSON and CSV;
- a repeated identical body reuses the same raw snapshot path;
- the existing content-addressed file is never overwritten with different bytes;
- metadata writes are atomic and symlink-safe;
- a failed fetch writes no raw or metadata artifact.

- [ ] **Step 2: Define the transport abstraction**

```python
@dataclass(frozen=True)
class FetchResponse:
    status_code: int
    headers: Mapping[str, str]
    chunks: Iterable[bytes]
    url: str
    peer_ip: str


class FetchTransport(Protocol):
    def get(self, url: str, *, timeout_seconds: float) -> FetchResponse:
        raise NotImplementedError


class AddressResolver(Protocol):
    def resolve(self, hostname: str) -> tuple[str, ...]:
        raise NotImplementedError
```

Implement `SystemAddressResolver` with `socket.getaddrinfo` and `RequestsFetchTransport` with `allow_redirects=False`. Redirect processing belongs to `snapshot_candidate`, not to `requests` automatic redirects. After each response, `peer_ip` must be non-denied and must appear in the address set approved immediately before that request; otherwise the fetch fails as a DNS-rebinding or proxy-route violation.

- [ ] **Step 3: Implement address and path safety**

```python
DENIED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4",
        "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
    )
)
```

Resolve all DNS answers and reject the URL if any answer is denied. Re-run this check after every redirect and compare the actual response `peer_ip` with the approved address set.

- [ ] **Step 4: Implement immutable storage**

Raw content path:

```text
evidence/raw/<sha256[0:2]>/<sha256>.<extension>
```

Metadata path:

```text
evidence/metadata/<artifact_id>.json
```

The metadata records candidate ID, original and final URL, redirect chain, status, headers allowlist, media type, byte count, SHA-256, fetch time, raw path, and provenance. It does not store cookies, authorization headers, or arbitrary response headers.

- [ ] **Step 5: Run tests and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_snapshot.py -q
rtk git add src/stock_research/research_project_v2_1/snapshot.py \
  tests/test_research_project_v2_1_snapshot.py
rtk git commit -m "feat: snapshot industry evidence safely"
```

## Task 7: PDF, HTML, CSV, And JSON Normalization

**Files:**

- Create: `src/stock_research/research_project_v2_1/parsers.py`
- Create: `src/stock_research/research_project_v2_1/normalize.py`
- Create: `artifacts/research_projects/v2_1/fixtures/documents/sample_engineering.html`
- Create: `artifacts/research_projects/v2_1/fixtures/documents/sample_capacity.csv`
- Create: `artifacts/research_projects/v2_1/fixtures/documents/sample_standard.json`
- Create: `tests/test_research_project_v2_1_parsers.py`

- [ ] **Step 1: Write failing parser tests**

HTML tests must remove `script`, `style`, navigation and hidden content while preserving headings, paragraphs, lists and table cells with locators.

PDF tests generate a small PDF fixture in the test and assert one normalized section per page with `page_start` and `page_end`.

CSV tests preserve header order, row numbers and typed string values. JSON tests sort object keys deterministically and preserve array indexes as JSON Pointer locators.

Invalid UTF-8, encrypted/unreadable PDF, oversized tables, and unsupported media types return stable parse errors and write no normalized artifact.

- [ ] **Step 2: Implement parser result types**

```python
@dataclass(frozen=True)
class ParsedSection:
    heading: str | None
    locator: str
    text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    parser: str
    media_type: str
    title: str | None
    sections: tuple[ParsedSection, ...]
```

- [ ] **Step 3: Implement normalized documents**

`normalize_document` creates stable section IDs and hashes:

```python
section_id = f"section:{artifact_id}:{index:04d}"
section_hash = content_sha256({
    "heading": section.heading,
    "locator": section.locator,
    "text": normalize_text(section.text),
})
```

The normalized document records artifact ID, parser name/version, media type, title, sections, document hash, parse timestamp, warnings, and provenance. Writes are atomic, managed-path contained, and immutable by content hash.

- [ ] **Step 4: Run tests and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_parsers.py -q
rtk git add src/stock_research/research_project_v2_1/parsers.py \
  src/stock_research/research_project_v2_1/normalize.py \
  artifacts/research_projects/v2_1/fixtures/documents \
  tests/test_research_project_v2_1_parsers.py
rtk git commit -m "feat: normalize industry evidence documents"
```

## Task 8: Independence, Freshness, Conflict, And Evidence Assessment

**Files:**

- Create: `src/stock_research/research_project_v2_1/evidence.py`
- Create: `tests/test_research_project_v2_1_evidence.py`

- [ ] **Step 1: Write failing evidence tests**

Test these cases:

- two URLs from the same publisher and same upstream document are not independent;
- verbatim or near-identical normalized section hashes are a republication relationship;
- a company filing and an industry association standard are independent source families;
- missing publish date returns `freshness=unknown`, never `fresh`;
- freshness is computed relative to an explicit `assessed_at`, never wall-clock time;
- support and opposition assessments for one claim produce `conflict_status=material_conflict`;
- one source cannot satisfy `minimum_coverage=2` by appearing through two mirrors;
- creating an assessment does not change `claim_status` or confidence;
- an assessment targeting a company or stock object is rejected in R2A.

- [ ] **Step 2: Implement source relationships**

```python
def assess_source_relationship(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    left_sections = set(left.get("section_hashes", ()))
    right_sections = set(right.get("section_hashes", ()))
    union = left_sections | right_sections
    section_overlap = (
        len(left_sections & right_sections) / len(union)
        if union
        else 0.0
    )
    if left["content_sha256"] == right["content_sha256"]:
        relationship = "same_document"
        reasons = ["raw content hashes match"]
    elif section_overlap >= 0.8:
        relationship = "republication"
        reasons = [f"normalized section hash Jaccard overlap is {section_overlap:.3f}"]
    elif left.get("upstream_source_id") and left.get("upstream_source_id") == right.get("upstream_source_id"):
        relationship = "shared_upstream_source"
        reasons = ["upstream source identifiers match"]
    elif left.get("publisher_family") and left.get("publisher_family") == right.get("publisher_family"):
        relationship = "same_publisher_family"
        reasons = ["publisher family identifiers match"]
    elif left.get("publisher_family") and right.get("publisher_family"):
        relationship = "independent"
        reasons = ["publisher families and content hashes differ"]
    else:
        relationship = "unknown"
        reasons = ["insufficient provenance to establish independence"]
    return {
        "left_artifact_id": left["artifact_id"],
        "right_artifact_id": right["artifact_id"],
        "relationship": relationship,
        "reasons": reasons,
    }
```

Return one of:

```text
same_document
republication
same_publisher_family
shared_upstream_source
independent
unknown
```

The result records reasons and input artifact IDs. Independence is never inferred solely from different domains.

- [ ] **Step 3: Implement freshness**

```python
def assess_freshness(
    publish_date: str | None,
    *,
    assessed_at: str,
    maximum_age_days: int,
) -> dict[str, Any]:
    if publish_date is None:
        return {
            "status": "unknown",
            "publish_date": None,
            "assessed_at": assessed_at,
            "age_days": None,
            "maximum_age_days": maximum_age_days,
        }
    published = datetime.date.fromisoformat(publish_date)
    assessed = datetime.datetime.fromisoformat(
        assessed_at.replace("Z", "+00:00")
    ).date()
    age_days = (assessed - published).days
    status = (
        "future_dated"
        if age_days < 0
        else "fresh"
        if age_days <= maximum_age_days
        else "stale"
    )
    return {
        "status": status,
        "publish_date": publish_date,
        "assessed_at": assessed_at,
        "age_days": age_days,
        "maximum_age_days": maximum_age_days,
    }
```

Return `fresh`, `stale`, `future_dated`, or `unknown`, with age and threshold fields.

- [ ] **Step 4: Implement industry Evidence Assessment**

```python
def build_industry_evidence_assessment(
    *,
    requirement: dict[str, Any],
    target: dict[str, Any],
    artifact: dict[str, Any],
    normalized_document: dict[str, Any],
    locator: str,
    evidence_role: str,
    assessment_summary: str,
    directness: str,
    strength: str,
    independence: str,
    freshness: str,
    scope_match: str,
    conflict_status: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    sections = {
        section["locator"]: section
        for section in normalized_document["sections"]
    }
    if locator not in sections:
        raise ResearchProjectV2Error(
            "Evidence locator does not resolve in the normalized document",
            code="RESEARCH_PROJECT_V2_1_EVIDENCE_LOCATOR_INVALID",
            details={"artifact_id": artifact["artifact_id"], "locator": locator},
        )
    assessment_id = (
        "industry_evidence_assessment:"
        + hashlib.sha256(
            f"{requirement['requirement_id']}\n{artifact['artifact_id']}\n{locator}".encode()
        ).hexdigest()[:24]
    )
    return {
        "assessment_id": assessment_id,
        "evidence_channel": "industry",
        "target_type": requirement["target_type"],
        "target_id": requirement["target_id"],
        "requirement_id": requirement["requirement_id"],
        "artifact_id": artifact["artifact_id"],
        "normalized_document_id": normalized_document["document_id"],
        "evidence_role": evidence_role,
        "locator": locator,
        "assessment_summary": assessment_summary,
        "directness": directness,
        "strength": strength,
        "independence": independence,
        "freshness": freshness,
        "scope_match": scope_match,
        "conflict_status": conflict_status,
        "review_status": "pending_review",
        "provenance": provenance,
    }
```

Allowed evidence roles are `supports`, `opposes`, `quantifies`, `defines`, and `boundary_evidence`. The assessment requires an exact locator that resolves inside the normalized document.

`write_industry_evidence_assessment` stores the immutable assessment at:

```text
evidence/assessments/<assessment_id>.json
```

The file includes a top-level content hash calculated with `content_hash` excluded. If the path already exists, identical canonical content is idempotent and different content raises `RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION`.

- [ ] **Step 5: Implement conflict summaries**

Group reviewed assessments by target. Count independent supporting, opposing and quantitative sources after collapsing source families. Return `none`, `limited`, `material_conflict`, or `unresolved`. Do not update claims automatically.

- [ ] **Step 6: Run tests and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_evidence.py -q
rtk git add src/stock_research/research_project_v2_1/evidence.py \
  tests/test_research_project_v2_1_evidence.py
rtk git commit -m "feat: assess industry evidence quality"
```

## Task 9: Industry Design Gate, Four Layered Projects, And V2.1 Index

**Files:**

- Create: `src/stock_research/research_project_v2_1/gates.py`
- Create: `src/stock_research/research_project_v2_1/maintenance.py`
- Create: `artifacts/research_projects/v2_1/projects/ai_compute_pcb_industry_bottleneck/**`
- Create: `artifacts/research_projects/v2_1/projects/humanoid_robot_industry_bottleneck/**`
- Create: `artifacts/research_projects/v2_1/projects/new_energy_storage_industry_bottleneck/**`
- Create: `artifacts/research_projects/v2_1/projects/high_end_medical_device_industry_bottleneck/**`
- Create: `artifacts/research_projects/v2_1/index/research_project_index_v2_1.json`
- Create: `artifacts/research_projects/v2_1/fixtures/valid/**`
- Create: `artifacts/research_projects/v2_1/fixtures/invalid/**`
- Create: `tests/test_research_project_v2_1_gates.py`
- Create: `tests/test_research_project_v2_1_pilots.py`

- [ ] **Step 1: Write failing Industry Design Gate tests**

The gate returns these checks in fixed order:

```text
INDUSTRY_LAYER_CORRECT
INDUSTRY_UPSTREAM_BASELINE_RESOLVED
INDUSTRY_PRIMARY_QUESTION_PRESENT
INDUSTRY_SCOPE_EXCLUDES_COMPANY_STOCK_RATING
INDUSTRY_REQUIRED_QUESTIONS_COVERED
INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS
INDUSTRY_COUNTER_SEARCH_PRESENT
INDUSTRY_SOURCE_CLASS_DIVERSITY
INDUSTRY_VALIDATION_PLAN_PRESENT
INDUSTRY_INVALIDATION_PLAN_PRESENT
INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS
INDUSTRY_PROVENANCE_COMPLETE
```

Mutations for a company layer, missing R1 baseline, no counter query, investment search terms, and a forbidden company list must each fail the exact check.

- [ ] **Step 2: Create four new layered projects**

Use these exact slugs and upstream R1 versions:

```text
ai_compute_pcb_industry_bottleneck
  → ai_compute_pcb_value_migration@0.1.0

humanoid_robot_industry_bottleneck
  → humanoid_robot_scale_up_bottlenecks@0.1.0

new_energy_storage_industry_bottleneck
  → new_energy_storage_route_competition@0.1.0

high_end_medical_device_industry_bottleneck
  → high_end_medical_device_commercialization@0.1.0
```

Each project uses `artifact_version=2.1.0`, `research_layer=industry_research`, a design-only `v0.1.0`, at least one Industry Evidence Requirement per required question and critical claim, and at least four Search Plans covering mechanism, quantification, counter evidence and primary engineering sources.

All candidate/artifact/document/assessment collections start empty. The project must not claim that evidence collection has occurred.

- [ ] **Step 3: Implement safe v2.1 maintenance**

`rebuild_layered_index(write: bool, layout: LayeredResearchLayout)` uses the R1 transaction and path-safety behavior but scans only `v2_1`. It fills placeholder hashes for unmanifested versions, appends manifest rows, and writes `research_project_index_v2_1.json` with `research_layer` in every row.

It rejects symlink paths, rolls back a partial batch, preserves existing manifest prefixes, and is byte-idempotent on a second write.

- [ ] **Step 4: Add valid and invalid fixtures**

Invalid fixtures must cover:

```text
missing research_layer
company_capture layer in R2A
missing upstream R1 version
upstream R1 content hash drift
Search Plan missing counter query
Search Plan containing stock terms
duplicate query ID
forbidden company capability collection
manifest hash mismatch
```

Each fixture has one intended failure and a correct self-hash unless hash mismatch is the intended failure.

- [ ] **Step 5: Run project acceptance tests**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_gates.py \
  tests/test_research_project_v2_1_pilots.py -q
```

Assert:

- exactly four v2.1 projects and exactly four unchanged R1 projects;
- every upstream reference resolves to the intended R1 content hash;
- every project passes Industry Design Gate;
- every company/stock output collection is absent, not merely empty;
- evidence collection arrays are empty in the design version;
- index rebuild is idempotent and never changes R1 bytes.

- [ ] **Step 6: Commit**

```bash
rtk git add src/stock_research/research_project_v2_1/gates.py \
  src/stock_research/research_project_v2_1/maintenance.py \
  artifacts/research_projects/v2_1 \
  tests/test_research_project_v2_1_gates.py \
  tests/test_research_project_v2_1_pilots.py
rtk git commit -m "data: seed layered industry research projects"
```

## Task 10: R2A CLI And Root Delegation

**Files:**

- Create: `src/stock_research/research_project_v2_1/cli.py`
- Modify: `src/stock_research/research_project_v2_1/__init__.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_research_project_v2_1_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Root command:

```text
research-project-v2-1
```

Subcommands:

```text
list
show
validate
gate
search-plan
discover
snapshot
parse
assess
audit
rebuild-index
```

Tests must verify raw root delegation, deterministic UTF-8 JSON, no traceback, and the exit codes below.

- [ ] **Step 2: Implement commands**

```text
list
  List only v2.1 layered projects.

show --project SLUG --version VERSION
  Show one immutable Industry Research version.

validate --all | --project SLUG [--version VERSION]
  Run schema, hash, manifest, common semantic and Industry semantic validation.

gate --project SLUG --version VERSION --gate industry-design
  Evaluate the 12 Industry Design checks.

search-plan --project SLUG --version VERSION
  Print Search Plans and requirement coverage without writing.

discover --search-plan FILE --results FILE [--write]
  Normalize imported discovery results. `--write` writes one immutable batch under `evidence/discovery`.

snapshot --candidate FILE [--write]
  Fetch and preview metadata; `--write` stores content-addressed raw and metadata artifacts.

parse --artifact-id ID [--write]
  Parse and preview a normalized document; `--write` stores it under evidence/normalized.

assess --assessment FILE [--write]
  Validate and preview an Industry Evidence Assessment; `--write` writes an immutable artifact under `evidence/assessments`, never edits a project version.

audit --project SLUG --version VERSION
  Audit upstream R1 references, Search Plan coverage, artifacts, normalized documents and assessment locators.

rebuild-index [--write]
  Safely rebuild only the v2.1 manifest/index generation.
```

- [ ] **Step 3: Implement exit codes**

```text
0  success / pass / pass_with_warnings / not_applicable
2  schema or semantic validation
3  evidence audit or Search Plan coverage failure
4  Industry Gate failure
5  hash, manifest, path or immutability violation
6  project, version, artifact or document not found
8  discovery or network snapshot failure
9  parser or normalization failure
10 unexpected runtime/I/O failure
```

Unexpected exceptions use `RESEARCH_PROJECT_V2_1_RUNTIME_ERROR`; domain envelopes include stable code, message and details.

- [ ] **Step 4: Wire the root command**

Add one import and one early branch to `src/stock_research/cli.py`:

```python
from stock_research.research_project_v2_1.cli import (
    run_research_project_v2_1_cli,
)


if raw_argv and raw_argv[0] == "research-project-v2-1":
    return run_research_project_v2_1_cli(raw_argv[1:])
```

Do not change the R1 `research-project-v2` command.

- [ ] **Step 5: Run CLI tests and help smoke**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_cli.py -q
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.cli research-project-v2-1 --help
```

Expected: all eleven commands appear and tests pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/stock_research/research_project_v2_1/cli.py \
  src/stock_research/research_project_v2_1/__init__.py \
  src/stock_research/cli.py \
  tests/test_research_project_v2_1_cli.py
rtk git commit -m "feat: expose industry evidence acquisition cli"
```

## Task 11: Operator Documentation, Scope Guard, And Final Verification

**Files:**

- Create: `docs/research_operating_layer_v2_r2a.md`
- Modify: `docs/research_operating_layer_v2_goal_and_roadmap.md`
- Modify: `tests/test_research_project_v2_1_scope_guard.py`

- [ ] **Step 1: Document R2A operations**

Required sections:

```text
Purpose
R1 And R2A Separation
Artifact Layout
Layered Identity And Versions
Industry Evidence Requirements
Search Plans
Source Discovery
Secure Snapshots
Document Normalization
Independence And Freshness
Industry Evidence Assessment
Industry Design Gate
CLI Commands
Exit Codes
Adding An Industry Project
R2A Non-goals
Production Migration Prohibition
Verification Evidence
```

Include one complete command example for every CLI subcommand, the fetch security defaults, append-only rules, and an explicit checklist forbidding company candidates, company ratings, stock prices, valuations and investment judgments.

- [ ] **Step 2: Generate a commit-attributed scope guard**

The scope test must derive changed paths from the approved R2A commit list and reject:

```text
artifacts/research_projects/v2/**
artifacts/theme_decomposition/**
artifacts/technology_industry_catalog/**
dashboard/**
src/stock_research/dashboard/**
database schema or migration paths
API route files
company/stock rating artifacts
```

The allowlist permits only `v2_1`, its package/tests/docs, `pyproject.toml` if a dependency change was approved, and the root CLI delegation.

- [ ] **Step 3: Run R2A and R1 test suites**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_1_*.py -q

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_*.py -q

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_theme_decomposition.py \
  tests/test_theme_company_mapping.py \
  tests/test_technology_industry_catalog.py \
  tests/test_dashboard_theme_research.py -q
```

Expected: zero failures. Existing deprecation warnings may remain documented but cannot be newly introduced by R2A code.

- [ ] **Step 4: Run the CLI acceptance matrix**

Run list, show, validate, gate, search-plan, imported discovery, fake-transport snapshot tests, parse fixtures, assessment validation, audit, rebuild dry-run and two writes. Record exact exit codes and verify the second rebuild creates no artifact diff.

- [ ] **Step 5: Verify all artifacts and forbidden-language rules**

Parse every v2.1 JSON/JSONL file. Search Industry projects, Search Plans, assessments and CLI fixtures for:

```text
company_rating
stock_rating
target_price
目标价
买入
卖出
股票推荐
watchlist_candidate
strategy_hypothesis
```

No layered Industry artifact may contain these output objects or recommendation language. Company names inside source metadata are permitted only when the source role is engineering, capacity, qualification or supply evidence.

- [ ] **Step 6: Update the roadmap only after verification passes**

Mark R2A complete only when schema, acquisition pipeline, four projects, CLI, scope guard, R1 regressions and security tests all pass. Do not mark R2B, R3, R4 or R5 complete.

- [ ] **Step 7: Commit**

```bash
rtk git add docs/research_operating_layer_v2_r2a.md \
  docs/research_operating_layer_v2_goal_and_roadmap.md \
  tests/test_research_project_v2_1_scope_guard.py
rtk git commit -m "docs: complete industry evidence acquisition r2a"
```

## Final Acceptance Checklist

- [ ] R1 `v2` bytes and exactly four R1 projects are unchanged.
- [ ] V1 Theme Research and Industry Catalog bytes are unchanged.
- [ ] `v2_1` has exactly four `industry_research` projects.
- [ ] Every layered project has an immutable reference to the intended R1 pilot version and hash.
- [ ] No R2A identity or version can use `company_capture` or `stock_evaluation`.
- [ ] Search Plans cover every required Industry Evidence Requirement and include counter-evidence searches.
- [ ] Discovery normalization is deterministic and filters investment-opinion results.
- [ ] Snapshot fetching rejects SSRF targets, unsafe redirects, oversized bodies and unsupported media.
- [ ] Raw, metadata and normalized artifacts are content-addressed, immutable and symlink-safe.
- [ ] HTML, PDF, CSV and JSON normalization preserves auditable locators.
- [ ] Independence, freshness and conflict results are explicit and deterministic.
- [ ] Evidence Assessment never changes a claim automatically.
- [ ] Industry Design Gate passes for all four layered projects.
- [ ] No company candidates, company ratings, stock ratings, prices, valuations or investment judgments exist.
- [ ] R2A, R1 and selected V1 regression tests pass.
- [ ] No production migration, API or Dashboard change exists.
- [ ] Final changed-file scope matches the R2A allowlist.
