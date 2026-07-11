# Technology Industry Catalog Wave 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a versioned, offline, read-only technology-industry catalog loader, validator, summary API, CLI, and ten-sector L1 artifact without touching the production database or dashboard.

**Architecture:** Store focused JSON files under `artifacts/technology_industry_catalog/v1/` and compose them through one Python loader. Validation uses stable error codes and enforces hierarchy, chain kind, decomposition method, unique canonical ownership, and typed references. The implementation follows existing Theme Decomposition loader and CLI conventions but remains storage-independent.

**Tech Stack:** Python 3.11+, standard-library `json`, `pathlib`, `argparse`, pytest, existing `stock-research` CLI.

---

## File Structure

- Create `src/stock_research/technology_industry_catalog.py`: loading, validation, lookup, summary, and module CLI.
- Modify `src/stock_research/cli.py`: delegate `technology-industry-catalog` commands.
- Create `tests/test_technology_industry_catalog.py`: loader, validation, summary, and CLI tests.
- Create `artifacts/technology_industry_catalog/v1/manifest.json`: version and package file layout.
- Create `artifacts/technology_industry_catalog/v1/sectors.json`: ten approved L1 sectors.
- Create `artifacts/technology_industry_catalog/v1/chains.json`: initially empty L2 list.
- Create `artifacts/technology_industry_catalog/v1/edges.json`: initially empty edge list.
- Create `artifacts/technology_industry_catalog/v1/sources.json`: catalog-scope sources.
- Create `artifacts/technology_industry_catalog/v1/nodes/.gitkeep`.
- Create `artifacts/technology_industry_catalog/v1/theme_compositions/.gitkeep`.

### Task 1: Define the package loader contract

**Files:**
- Create: `tests/test_technology_industry_catalog.py`
- Create: `src/stock_research/technology_industry_catalog.py`

- [ ] **Step 1: Write the failing loader test**

Create a temporary package helper and this test:

```python
def test_load_industry_catalog_composes_package_files(tmp_path: Path):
    root = _write_catalog_package(tmp_path)

    catalog = load_industry_catalog(root)

    assert catalog["artifact_version"] == "technology_industry_catalog_v1"
    assert [row["sector_id"] for row in catalog["sectors"]] == ["semiconductor_electronics"]
    assert [row["chain_id"] for row in catalog["chains"]] == ["semiconductor_equipment"]
    assert [row["node_id"] for row in catalog["nodes"]] == ["lithography", "duv_lithography"]
    assert catalog["edges"] == []
    assert catalog["theme_compositions"] == []
```

The helper must write valid `manifest.json`, `sectors.json`, `chains.json`, `edges.json`, `sources.json`, and `nodes/semiconductor_equipment.json` using UTF-8 JSON.

- [ ] **Step 2: Run the test and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py::test_load_industry_catalog_composes_package_files -q
```

Expected: collection fails because `stock_research.technology_industry_catalog` does not exist.

- [ ] **Step 3: Implement minimal package loading**

Define:

```python
CATALOG_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "technology_industry_catalog" / "v1"
CATALOG_ARTIFACT_VERSION = "technology_industry_catalog_v1"
CHAIN_KINDS = {
    "canonical_industry_chain",
    "application_theme_chain",
    "frontier_technology_chain",
}
DECOMPOSITION_METHODS = {
    "manufacturing_process",
    "system_architecture",
    "infrastructure_flow",
    "technical_route",
}
NODE_LEVELS = {"L3", "L4"}
NODE_KINDS = {"canonical", "application_role", "frontier_route"}
EDGE_TYPES = {
    "depends_on", "enables", "supplies", "uses", "substitutes",
    "competes_with", "downstream_of",
}
CATALOG_STATUSES = {"skeleton", "draft", "reviewed", "published"}


class IndustryCatalogValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code
```

Implement `load_industry_catalog(artifact_dir=None)` to read the manifest, named registry files, sorted node files, and sorted composition files, then call `_validate_catalog`.

- [ ] **Step 4: Run the test and verify pass**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py::test_load_industry_catalog_composes_package_files -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/technology_industry_catalog.py tests/test_technology_industry_catalog.py
git commit -m "feat: add technology industry catalog loader"
```

### Task 2: Enforce hierarchy and ownership validation

**Files:**
- Modify: `tests/test_technology_industry_catalog.py`
- Modify: `src/stock_research/technology_industry_catalog.py`

- [ ] **Step 1: Add failing stable-code tests**

Add mutation tests covering:

```python
EXPECTED_CODES = {
    "duplicate_sector": "DUPLICATE_SECTOR_ID",
    "orphan_chain_sector": "ORPHAN_CHAIN_SECTOR",
    "invalid_chain_kind": "INVALID_CHAIN_KIND",
    "invalid_decomposition_method": "INVALID_DECOMPOSITION_METHOD",
    "duplicate_node": "DUPLICATE_NODE_ID",
    "orphan_node_parent": "ORPHAN_NODE_PARENT",
    "orphan_node_chain": "ORPHAN_NODE_CHAIN",
    "invalid_node_level": "INVALID_NODE_LEVEL",
    "invalid_node_kind_for_chain": "INVALID_NODE_KIND_FOR_CHAIN",
    "duplicate_canonical_key": "DUPLICATE_CANONICAL_OWNERSHIP",
    "invalid_primary_path": "INVALID_PRIMARY_PATH",
    "orphan_edge_source": "ORPHAN_EDGE_SOURCE",
    "orphan_edge_target": "ORPHAN_EDGE_TARGET",
    "invalid_canonical_reference": "INVALID_CANONICAL_NODE_REFERENCE",
}
```

Also assert L3 parents are null, L4 parents are L3 nodes in the same chain, and application roles cannot own canonical keys.

- [ ] **Step 2: Run tests and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py -q
```

Expected: validation assertions fail.

- [ ] **Step 3: Implement deterministic validators**

Use these required fields:

```python
SECTOR_FIELDS = {"sector_id", "sector_name", "description", "status", "order"}
CHAIN_FIELDS = {
    "chain_id", "sector_id", "chain_name", "chain_kind", "decomposition_method",
    "description", "scope", "exclusions", "aliases", "status", "order",
}
NODE_FIELDS = {
    "node_id", "chain_id", "parent_node_id", "level", "node_name", "node_kind",
    "node_type", "description", "status", "primary_path", "canonical_key",
    "canonical_node_refs",
}
EDGE_FIELDS = {
    "edge_id", "source_node_id", "target_node_id",
    "relationship_type", "notes", "source_ids",
}
COMPOSITION_FIELDS = {
    "composition_id", "chain_id", "role_node_id", "canonical_node_refs",
    "relationship_type", "notes",
}
SOURCE_FIELDS = {"source_id", "title", "publisher", "url", "source_type", "notes"}
```

Split validation into `_validate_sectors`, `_validate_chains`, `_validate_nodes`, `_validate_edges`, and `_validate_theme_compositions`. For canonical L4 nodes require:

```python
primary_path == [sector_id, chain_id, parent_node_id, node_id]
```

Reject the second occurrence of any non-empty `canonical_key`.

- [ ] **Step 4: Run tests and verify pass**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/technology_industry_catalog.py tests/test_technology_industry_catalog.py
git commit -m "feat: validate technology industry hierarchy"
```

### Task 3: Add stable lookup and summary functions

**Files:**
- Modify: `tests/test_technology_industry_catalog.py`
- Modify: `src/stock_research/technology_industry_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
def test_catalog_summary_separates_chain_kinds(tmp_path: Path):
    summary = summarize_industry_catalog(
        load_industry_catalog(_write_catalog_package(tmp_path))
    )
    assert summary == {
        "sector_count": 1,
        "chain_count": 1,
        "l3_node_count": 1,
        "l4_node_count": 1,
        "edge_count": 0,
        "theme_composition_count": 0,
        "chains_by_kind": {"canonical_industry_chain": 1},
        "chains_by_status": {"draft": 1},
        "chains_by_sector": {"semiconductor_electronics": 1},
        "nodes_by_status": {"draft": 2},
    }


def test_get_industry_chain_returns_nodes_and_edges(tmp_path: Path):
    catalog = load_industry_catalog(_write_catalog_package(tmp_path))
    detail = get_industry_chain(catalog, "semiconductor_equipment")
    assert detail["chain"]["chain_id"] == "semiconductor_equipment"
    assert [row["node_id"] for row in detail["nodes"]] == [
        "lithography", "duv_lithography",
    ]
```

Add a `CHAIN_NOT_FOUND` test.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py -q
```

Expected: new public functions are missing.

- [ ] **Step 3: Implement functions**

Add:

```python
def summarize_industry_catalog(catalog: dict[str, Any]) -> dict[str, Any]: ...
def get_industry_chain(catalog: dict[str, Any], chain_id: str) -> dict[str, Any]: ...
```

Sort summary keys and returned nodes deterministically by `(level, node_id)`.

- [ ] **Step 4: Run tests and commit**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py -q
git add src/stock_research/technology_industry_catalog.py tests/test_technology_industry_catalog.py
git commit -m "feat: summarize technology industry catalog"
```

Expected: tests pass.

### Task 4: Add module and platform CLI commands

**Files:**
- Modify: `tests/test_technology_industry_catalog.py`
- Modify: `src/stock_research/technology_industry_catalog.py`
- Modify: `src/stock_research/cli.py`

- [ ] **Step 1: Write failing CLI tests**

Test:

```text
technology-industry-catalog validate
technology-industry-catalog summary
technology-industry-catalog show --chain semiconductor_equipment
```

Require exit code 0 and JSON stdout on success. Require exit code 2 and this shape on validation failure:

```json
{"status":"error","error_code":"INVALID_CHAIN_KIND","message":"..."}
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py -q
```

Expected: `cli` is missing.

- [ ] **Step 3: Implement module CLI**

Use `argparse`, `ensure_ascii=False`, sorted keys, and the same error handling pattern as `theme_decomposition.cli`.

- [ ] **Step 4: Add platform delegation**

Import:

```python
from stock_research.technology_industry_catalog import cli as run_technology_industry_catalog_cli
```

Add fast dispatch in `main_for_args`:

```python
if raw_argv and raw_argv[0] == "technology-industry-catalog":
    return run_technology_industry_catalog_cli(raw_argv[1:])
```

Register an argparse remainder command matching `theme-decomposition`.

- [ ] **Step 5: Run tests and commit**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py -q
git add src/stock_research/technology_industry_catalog.py src/stock_research/cli.py tests/test_technology_industry_catalog.py
git commit -m "feat: expose technology industry catalog cli"
```

Expected: all tests pass.

### Task 5: Add the repository L1 artifact

**Files:**
- Create: `artifacts/technology_industry_catalog/v1/manifest.json`
- Create: `artifacts/technology_industry_catalog/v1/sectors.json`
- Create: `artifacts/technology_industry_catalog/v1/chains.json`
- Create: `artifacts/technology_industry_catalog/v1/edges.json`
- Create: `artifacts/technology_industry_catalog/v1/sources.json`
- Create: `artifacts/technology_industry_catalog/v1/nodes/.gitkeep`
- Create: `artifacts/technology_industry_catalog/v1/theme_compositions/.gitkeep`
- Modify: `tests/test_technology_industry_catalog.py`

- [ ] **Step 1: Write the failing repository test**

Assert exact ordered sector IDs:

```python
EXPECTED_SECTOR_IDS = [
    "semiconductor_electronics",
    "next_generation_information_technology",
    "high_end_equipment_intelligent_manufacturing",
    "energy_technology_new_power_system",
    "advanced_materials",
    "intelligent_vehicles_advanced_transportation",
    "aerospace_low_altitude_ocean_technology",
    "life_sciences_medical_technology",
    "green_low_carbon_resource_recycling",
    "frontier_future_technology",
]
```

Also assert `catalog["chains"] == []`.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py::test_repository_catalog_starts_with_ten_approved_sectors -q
```

Expected: artifact directory not found.

- [ ] **Step 3: Create artifacts**

Use artifact version `technology_industry_catalog_v1`, catalog ID `technology_industry_catalog_cn_v1`, status `draft`, and update date `2026-07-11`. Add the ten approved sectors in order. Add the seven external sources from the approved design spec. Keep chains, edges, nodes, and compositions empty.

- [ ] **Step 4: Verify and commit**

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
.venv/bin/pytest tests/test_technology_industry_catalog.py tests/test_theme_decomposition.py tests/test_decomposition_templates.py -q
git add artifacts/technology_industry_catalog/v1 tests/test_technology_industry_catalog.py
git commit -m "data: add technology industry sector catalog"
```

Expected: CLI reports `sector_count: 10`, `chain_count: 0`; tests pass.

### Task 6: Final Wave 1 verification

**Files:**
- Verify only.

- [ ] **Step 1: Check diffs**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 2: Run verification matrix**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py tests/test_theme_decomposition.py tests/test_decomposition_templates.py tests/test_theme_research_phase_verifier.py -q
.venv/bin/python -m stock_research.cli technology-industry-catalog summary
```

Expected: tests pass; summary reports ten sectors and zero L2 chains.

- [ ] **Step 3: Confirm scope isolation**

```bash
git diff --name-only HEAD~4..HEAD
```

Expected: only the catalog module, its tests/artifacts, and CLI delegation changed. No dashboard, database schema, Theme Research store, or Tech Bottleneck production files changed.
