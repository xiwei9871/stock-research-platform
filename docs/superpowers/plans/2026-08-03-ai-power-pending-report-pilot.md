# AI Power Pending Report Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the formal Theme Research report-review workflow on the current production baseline, generate one immutable AI power-supply report draft, index it as `pending_review`, and leave it ready for the `admin` user's human review without publishing it.

**Architecture:** Create a clean release worktree from production commit `082b9ca8`, merge the completed report workflow, and add a deterministic backend generator that reads validated canonical Theme Research packages. The generator atomically finalizes Markdown plus a v1 manifest; the existing indexer registers it through the indexer role, and the existing admin UI previews it while approved-user APIs continue to expose only published history.

**Tech Stack:** Python 3.12+, dataclasses, pathlib/os, SHA-256/JSON, PostgreSQL 16, FastAPI, React/TypeScript/Vite, pytest, Vitest, Playwright, Docker Compose, nginx.

---

## File Map

**Create:**

- `src/stock_research/theme_research_report_generator.py` — validated input loading, deterministic Markdown rendering, atomic finalization, CLI.
- `tests/test_theme_research_report_generator.py` — renderer, guardrail, manifest, overwrite, and atomic-failure tests.
- `docs/ops/ai-power-pending-report-pilot.md` — exact production runbook and rollback boundary.

**Reuse after merging the report workflow:**

- `src/stock_research/theme_research_report_manifest.py`
- `src/stock_research/theme_research_report_index.py`
- `src/stock_research/theme_research_report_store.py`
- `src/stock_research/theme_research_report_schema.py`
- `src/stock_research/dashboard/app.py`
- `dashboard/src/components/ThemeResearchReportReviewWorkspace.tsx`
- `deploy/sync_dashboard_release.sh`

## Task 1: Create a production-based integration worktree

**Files:**

- Worktree: `/Users/xiwei/stock_research_release_ai_power_pending_20260803`
- Base: `082b9ca8879edf5ea603c33099124f52badb01e7`
- Merge source: `5ffd4443`

- [ ] **Step 1: Verify the approved source branch is clean**

Run:

```bash
rtk git -C /Users/xiwei/stock_research_release_20260801 status --short
rtk git -C /Users/xiwei/stock_research_release_20260801 rev-parse HEAD
rtk git -C /Users/xiwei/stock_research cat-file -e 082b9ca8879edf5ea603c33099124f52badb01e7^{commit}
```

Expected: clean source worktree, HEAD `5ffd444...`, production commit present.

- [ ] **Step 2: Create the isolated worktree**

Run:

```bash
rtk git -C /Users/xiwei/stock_research worktree add \
  -b release/ai-power-pending-20260803 \
  /Users/xiwei/stock_research_release_ai_power_pending_20260803 \
  082b9ca8879edf5ea603c33099124f52badb01e7
```

Expected: a clean worktree. Do not edit or clean `/Users/xiwei/stock_research`, which contains unrelated user changes.

- [ ] **Step 3: Merge the approved report workflow**

Run in the new worktree:

```bash
rtk git merge --no-ff 5ffd4443 -m "merge: restore theme report workflow on production baseline"
```

If `tests/test_dashboard_release_scripts.py` conflicts, retain both the 22:00 scheduler assertion and report release checks:

```python
assert "<integer>22</integer>" in plist
assert "check_theme_research_report_runtime.py" in release_script
assert "THEME_RESEARCH_REPORT_HOST_ROOT" in release_script
```

Run:

```bash
rtk git diff --check
rtk git status --short
rtk rg -n "22|StartCalendarInterval" deploy/launchd/com.stockresearch.dashboard-daily-sync.plist
rtk rg -n "api/admin/theme-research/reports|report-index/status" src/stock_research/dashboard/app.py
```

Expected: no conflict markers, 22:00 preserved, report admin routes present.

## Task 2: Write failing generator tests

**Files:**

- Create: `tests/test_theme_research_report_generator.py`
- Create later in Task 3: `src/stock_research/theme_research_report_generator.py`

- [ ] **Step 1: Define the fixture and renderer contract**

Create the test file with:

```python
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from stock_research.theme_research_report_generator import (
    PILOT_THEME_ID,
    PilotReportGenerationError,
    PilotReportInputs,
    generate_ai_power_pending_report,
    render_ai_power_report_markdown,
)
from stock_research.theme_research_report_manifest import (
    ReportManifestLimits,
    load_report_manifest,
)

GENERATED_AT = datetime.fromisoformat("2026-08-03T10:00:00+08:00")


def pilot_inputs() -> PilotReportInputs:
    return PilotReportInputs(
        theme={
            "theme_id": PILOT_THEME_ID,
            "theme_name": "AI供电产业链",
            "summary": "AI算力基础设施的供电、散热与配套价值链。",
            "status": "reviewed",
        },
        nodes=({
            "node_id": "server_power_supply",
            "node_name": "服务器电源",
            "node_type": "core_component",
            "description": "服务器侧电源转换与供电。",
            "value_capture_score": 5,
            "bottleneck_score": 4,
            "localization_gap_score": 3,
            "supply_tightness_score": 3,
            "evidence_strength": 4,
            "node_review_status": "reviewed",
        },),
        sources=({
            "source_id": "source-1",
            "title": "公司年度报告",
            "publisher": "示例公司",
            "publish_date": "2026-03-31",
            "reliability_level": "S1",
            "review_status": "accepted",
            "url_or_ref": "local:source-1",
        },),
        claims=({
            "claim_id": "claim-1",
            "claim_text": "高功率密度提升电源与散热要求。",
            "claim_type": "bottleneck",
            "confidence": 0.9,
            "evidence_status": "verified",
            "platform_use_status": "reviewed",
            "supporting_source_ids": ["source-1"],
        },),
        company_mappings=({
            "mapping_id": "mapping-1",
            "company_code": "300870.SZ",
            "company_name": "欧陆通",
            "mapped_node_id": "server_power_supply",
            "business_materiality": "meaningful_segment",
            "relationship_summary": "服务器电源相关业务。",
            "review_status": "reviewed",
            "evidence_ids": ["evidence-1"],
        },),
        node_priorities=({
            "node_id": "server_power_supply",
            "priority_score": 78.0,
            "priority_class": "deep_research_priority",
            "recommended_action": "deep_node_research",
        },),
        company_priorities=({
            "mapping_id": "mapping-1",
            "company_research_priority_score": 75.6,
            "priority_band": "high",
            "integration_status": "linked_existing_universe",
            "existing_review_context": {"status": "pending_review"},
        },),
        evidence_gaps=({
            "node_id": "transformer",
            "node_name": "变压器",
            "evidence_gap_score": 3,
            "recommended_action": "collect_node_evidence",
        },),
        artifact_versions=("theme_decomposition_v1_6",),
    )
```

- [ ] **Step 2: Add deterministic rendering assertions**

```python
def test_render_ai_power_report_is_deterministic_and_review_only():
    first = render_ai_power_report_markdown(pilot_inputs(), generated_at=GENERATED_AT)
    second = render_ai_power_report_markdown(pilot_inputs(), generated_at=GENERATED_AT)
    assert first == second
    for heading in (
        "# AI供电产业链分析报告",
        "## 核心结论与研究边界",
        "## 产业链结构",
        "## 价值量与关键瓶颈",
        "## 重点公司映射",
        "## 证据强弱与待补缺口",
        "## 风险、反证与局限",
        "## 来源索引",
        "## Admin 人工审核清单",
    ):
        assert heading in first
    assert "source-1" in first
    assert "claim-1" in first
    assert "不构成投资建议" in first
    assert all(phrase not in first for phrase in ("目标价", "买入", "卖出"))
```

- [ ] **Step 3: Add manifest and immutable-version assertions**

```python
def test_generate_writes_valid_markdown_manifest_and_no_pdf(tmp_path: Path):
    result = generate_ai_power_pending_report(
        inputs=pilot_inputs(),
        report_root=tmp_path,
        version="2026-08-03.1",
        generated_at=GENERATED_AT,
        pipeline_run_id="pilot-run-1",
    )
    version_dir = tmp_path / PILOT_THEME_ID / "2026-08-03.1"
    markdown = (version_dir / "report.md").read_bytes()
    manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["version_dir"] == str(version_dir)
    assert manifest["title"] == "AI供电产业链分析报告"
    assert manifest["artifacts"] == {"markdown": {
        "path": "report.md",
        "sha256": hashlib.sha256(markdown).hexdigest(),
    }}
    assert manifest["metadata"]["pipeline_run_id"] == "pilot-run-1"
    assert manifest["metadata"]["research_only"] is True
    assert not (version_dir / "report.pdf").exists()
    loaded = load_report_manifest(
        version_dir / "manifest.json",
        report_root=tmp_path,
        limits=ReportManifestLimits(65536, 10485760, 52428800),
    )
    assert loaded.theme_id == PILOT_THEME_ID
    assert loaded.pdf is None


def test_generate_rejects_existing_version(tmp_path: Path):
    kwargs = dict(
        inputs=pilot_inputs(),
        report_root=tmp_path,
        version="2026-08-03.1",
        generated_at=GENERATED_AT,
    )
    generate_ai_power_pending_report(**kwargs, pipeline_run_id="pilot-run-1")
    with pytest.raises(PilotReportGenerationError, match="already exists"):
        generate_ai_power_pending_report(**kwargs, pipeline_run_id="pilot-run-2")
```

- [ ] **Step 4: Add atomic-failure and trading-language tests**

```python
def test_failed_rename_leaves_no_final_or_staging_directory(tmp_path: Path, monkeypatch):
    from stock_research import theme_research_report_generator as generator
    monkeypatch.setattr(
        generator.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("rename failed")),
    )
    with pytest.raises(OSError, match="rename failed"):
        generate_ai_power_pending_report(
            inputs=pilot_inputs(), report_root=tmp_path,
            version="2026-08-03.1", generated_at=GENERATED_AT,
            pipeline_run_id="rename-failure",
        )
    assert not (tmp_path / PILOT_THEME_ID / "2026-08-03.1").exists()
    assert list(tmp_path.glob(".staging-*")) == []


def test_trading_language_fails_before_finalization(tmp_path: Path, monkeypatch):
    from stock_research import theme_research_report_generator as generator
    monkeypatch.setattr(generator, "render_ai_power_report_markdown", lambda *_a, **_k: "建议买入")
    with pytest.raises(PilotReportGenerationError, match="prohibited trading language"):
        generate_ai_power_pending_report(
            inputs=pilot_inputs(), report_root=tmp_path,
            version="2026-08-03.1", generated_at=GENERATED_AT,
            pipeline_run_id="guardrail",
        )
    assert not (tmp_path / PILOT_THEME_ID / "2026-08-03.1").exists()


def test_generator_cli_help_is_available():
    result = subprocess.run(
        [sys.executable, "-m", "stock_research.theme_research_report_generator", "--help"],
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--repository-root" in result.stdout
    assert "--report-root" in result.stdout
    assert "--pipeline-run-id" in result.stdout
```

- [ ] **Step 5: Run and verify RED**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_theme_research_report_generator.py -q
```

Expected: collection fails because `theme_research_report_generator` does not exist.

## Task 3: Implement the deterministic generator

**Files:**

- Create: `src/stock_research/theme_research_report_generator.py`
- Test: `tests/test_theme_research_report_generator.py`

- [ ] **Step 1: Define public types, constants, and validated loader**

Implement:

```python
PILOT_THEME_ID = "ai_power_value_capture_v1"
GENERATOR_NAME = "theme-research-report-pipeline"
GENERATOR_VERSION = "1.0.0"
_VERSION_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[1-9][0-9]*$")
_PROHIBITED = ("买入", "卖出", "目标价", "buy recommendation", "sell recommendation")


class PilotReportGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class PilotReportInputs:
    theme: dict[str, Any]
    nodes: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    claims: tuple[dict[str, Any], ...]
    company_mappings: tuple[dict[str, Any], ...]
    node_priorities: tuple[dict[str, Any], ...]
    company_priorities: tuple[dict[str, Any], ...]
    evidence_gaps: tuple[dict[str, Any], ...]
    artifact_versions: tuple[str, ...]
```

`load_ai_power_report_inputs(repository_root, theme_id=PILOT_THEME_ID)` must call `load_theme`, `load_theme_company_mapping_package`, and `load_theme_research_priority_package`, filter every row to the pilot theme, and sort by stable IDs. It must reject every other theme ID.

- [ ] **Step 2: Implement the fixed Markdown sections**

`render_ai_power_report_markdown()` must emit, in this order:

```python
SECTIONS = (
    "# AI供电产业链分析报告",
    "## 核心结论与研究边界",
    "## 产业链结构",
    "## 价值量与关键瓶颈",
    "### 供电、液冷、电网与数据中心配套",
    "## 重点公司映射",
    "## 证据强弱与待补缺口",
    "## 风险、反证与局限",
    "## 来源索引",
    "### 观点索引",
    "## Admin 人工审核清单",
)
```

Use Markdown tables for nodes, priority scores, companies, and sources. Include stable `node_id`, `mapping_id`, `source_id`, and `claim_id` values. Sort by score descending and stable ID ascending. Escape pipes and newlines with `_cell()`. End with an admin checklist and the exact research-only statement `仅用于研究与人工审核，不构成投资建议，不用于信号或准入。`

- [ ] **Step 3: Implement guardrails and atomic finalization**

Implement the exact public signature:

```python
def generate_ai_power_pending_report(
    *,
    inputs: PilotReportInputs,
    report_root: Path,
    version: str,
    generated_at: datetime,
    pipeline_run_id: str,
) -> dict[str, Any]:
```

Required behavior:

```python
root = report_root.absolute()
theme_dir = root / PILOT_THEME_ID
final_dir = theme_dir / version
staging = Path(tempfile.mkdtemp(prefix=f".staging-{pipeline_run_id}-", dir=root))
```

Validate the theme, timezone-aware timestamp, version regex, safe run ID, non-empty canonical collections, and absent final directory before writing. Write UTF-8 `report.md`, calculate SHA-256, then write `manifest.json` last with this shape:

```python
manifest = {
    "schema_version": "theme_research_report_manifest_v1",
    "theme_id": PILOT_THEME_ID,
    "version": version,
    "title": "AI供电产业链分析报告",
    "summary": "基于现有主题节点、公司映射、证据与研究优先级生成的人工审核初稿。",
    "generated_at": generated_at.isoformat(),
    "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
    "artifacts": {"markdown": {"path": "report.md", "sha256": markdown_sha256}},
    "metadata": {
        "pipeline_run_id": pipeline_run_id,
        "artifact_versions": list(inputs.artifact_versions),
        "node_count": len(inputs.nodes),
        "company_mapping_count": len(inputs.company_mappings),
        "source_count": len(inputs.sources),
        "claim_count": len(inputs.claims),
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    },
}
```

Set final file modes `0440`, staging directory `0550`, fsync files/directories, and call `os.replace(staging, final_dir)`. A `finally` block removes only a still-existing staging directory. Never overwrite `final_dir`.

- [ ] **Step 4: Add the CLI**

Support:

```text
--repository-root PATH
--report-root PATH
--theme-id ai_power_value_capture_v1
--version 2026-08-03.1
--generated-at 2026-08-03T10:00:00+08:00
--pipeline-run-id STRING
```

The CLI loads inputs, generates the version, prints one JSON result, and exits zero. Validation errors print no success JSON and exit nonzero.

- [ ] **Step 5: Run GREEN and regressions**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_theme_research_report_generator.py \
  tests/test_theme_research_report_manifest.py \
  tests/test_theme_research_report_index.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/stock_research/theme_research_report_generator.py tests/test_theme_research_report_generator.py
rtk git commit -m "feat: generate ai power report review pilot"
```

## Task 4: Add the production runbook

**Files:**

- Create: `docs/ops/ai-power-pending-report-pilot.md`

- [ ] **Step 1: Write the runbook**

Create `docs/ops/ai-power-pending-report-pilot.md` with these immutable values and gates:

```markdown
# AI Power Pending Report Pilot Runbook

- Theme: `ai_power_value_capture_v1`
- Version: `2026-08-03.1`
- Title: `AI供电产业链分析报告`
- Target database state: `pending_review`
- Publish/reject action: prohibited during this runbook

## Required order

1. Confirm the deployed code includes the current production tip and report workflow.
2. Confirm the version directory and database row do not exist.
3. Generate Markdown and manifest in the one-shot writable generator container.
4. Validate final bytes in a read-only container.
5. Run the one-shot indexer through `theme_research_report_indexer`.
6. Confirm one pending row and one initial system audit event.
7. Confirm admin preview and approved-user invisibility.
8. Leave the version pending.

## Retry boundary

Never overwrite a final version. Before indexing, preserve and quarantine invalid final bytes before using a new version number. After indexing, all corrections use a new immutable version.
```

- [ ] **Step 2: Run release/documentation tests**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_release_scripts.py \
  tests/test_platform_external_access_deploy_docs.py -q
rtk bash -n deploy/check_dashboard_release.sh deploy/sync_dashboard_release.sh
rtk git diff --check
```

Expected: zero failures and zero shell syntax errors.

- [ ] **Step 3: Commit**

```bash
rtk git add docs/ops/ai-power-pending-report-pilot.md
rtk git commit -m "docs: add ai power pending report runbook"
```

## Task 5: Run the complete isolated verification

**Files:** No new files unless a failing regression requires a focused fix.

- [ ] **Step 1: Run backend report tests**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_theme_research_report_generator.py \
  tests/test_theme_research_report_manifest.py \
  tests/test_theme_research_report_index.py \
  tests/test_theme_research_report_runtime_check.py \
  tests/test_dashboard_theme_research_reports.py \
  tests/integration/test_theme_research_report_store_postgres.py -q
```

Expected: zero failures. Do not skip the PostgreSQL tests; repair the isolated test service if unavailable.

- [ ] **Step 2: Run frontend report tests and build**

From `dashboard/`:

```bash
rtk pnpm install --frozen-lockfile
rtk pnpm test -- client.test.ts theme-research-report-review.test.tsx theme-research-report-reader.test.tsx app-shell.test.tsx
rtk pnpm build
```

Expected: selected Vitest tests pass and the production build exits zero.

- [ ] **Step 3: Run real-backend report E2E**

From `dashboard/`:

```bash
rtk pnpm test:e2e:theme-reports
```

Expected: the isolated normal user cannot see pending content, the admin can preview it, and publish/reject transitions still pass in the isolated fixture.

- [ ] **Step 4: Generate and validate a local canary**

Create `PILOT_TMP_REPORT_ROOT` with `mktemp -d`, then run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.theme_research_report_generator \
  --repository-root "$PWD" \
  --report-root "$PILOT_TMP_REPORT_ROOT" \
  --theme-id ai_power_value_capture_v1 \
  --version 2026-08-03.1 \
  --generated-at 2026-08-03T10:00:00+08:00 \
  --pipeline-run-id local-pilot-canary
```

Validate with `load_report_manifest`; expected title, theme, version, Markdown checksum, and `pdf is None`. Run the indexer against the isolated database and require first-scan `indexed=1, invalid=0`, then second-scan `unchanged=1, invalid=0`.

- [ ] **Step 5: Record a clean release candidate**

```bash
rtk git diff --check
rtk git status --short
rtk git rev-parse HEAD
```

Expected: clean worktree. Store the full SHA as `PILOT_RELEASE_ID`.

## Task 6: Deploy the workflow with an empty queue

**Systems:**

- Remote root: `/home/jqz/code/stock-research-platform-main`
- Report root: `/home/jqz/code/stock-research-platform-main/reports/theme-research`
- External URL: `https://stock.manqiaotechnology.com`

- [ ] **Step 1: Reconcile the live production tip**

Read `/api/platform/readiness` and `/release.json`. If the live SHA is newer than `082b9ca8`, stop, merge that live commit into the release worktree, rerun Tasks 5.1–5.5, and only then continue. Never overwrite a newer production release.

- [ ] **Step 2: Verify the empty production state**

Require:

```text
report root file count == 0
pilot final directory absent
research.theme_research_report_version row count == 0
```

If any report appears, stop and revise the immutable version and acceptance counts.

- [ ] **Step 3: Run the canonical release**

Use the existing secure sync environment and set:

```text
STOCK_RESEARCH_RELEASE_ROOT=<clean integration worktree>
EXPECTED_TRADE_DATE=2026-07-31
DASHBOARD_REMOTE_ENV_FILE=.dashboard_runtime_env
DASHBOARD_LOGIN_USERNAME=admin
THEME_RESEARCH_REPORT_HOST_ROOT=/home/jqz/code/stock-research-platform-main/reports/theme-research
```

Run `deploy/sync_dashboard_release.sh`. Expected: schema version, independent runtime/indexer/reviewer roles, read-only report mount, index diagnostics, release provenance, and external gate all pass for `PILOT_RELEASE_ID`.

- [ ] **Step 4: Verify the restored empty admin queue**

With an authenticated admin session, require:

```json
{"total": 0, "items": []}
```

from `GET /api/admin/theme-research/reports?status=pending_review`, and require `/api/admin/theme-research/report-index/status` to report `status=ok`, `invalid=0`, and `errors=[]`.

## Task 7: Generate and index the production pilot

**Final directory:**

`/home/jqz/code/stock-research-platform-main/reports/theme-research/ai_power_value_capture_v1/2026-08-03.1`

- [ ] **Step 1: Recheck immutable identity immediately before generation**

Require the final directory to be absent, the matching database row count to be zero, and no `.staging-production-ai-power-pilot-20260803-*` directory to exist.

- [ ] **Step 2: Run the one-shot generator container**

Run `stock-research-dashboard-api:${PILOT_RELEASE_ID}` as the deployment user's uid/gid with:

```text
/home/jqz/code/stock-research-platform-main/artifacts/theme_decomposition -> /app/artifacts/theme_decomposition:ro
/home/jqz/code/stock-research-platform-main/outputs -> /app/outputs:ro
/home/jqz/code/stock-research-platform-main/reports/theme-research -> /app/reports/theme-research:rw
```

Container command:

```bash
python -m stock_research.theme_research_report_generator \
  --repository-root /app \
  --report-root /app/reports/theme-research \
  --theme-id ai_power_value_capture_v1 \
  --version 2026-08-03.1 \
  --generated-at 2026-08-03T10:00:00+08:00 \
  --pipeline-run-id production-ai-power-pilot-20260803
```

Expected: one success JSON object and exactly `report.md` plus `manifest.json` in the final directory. The long-running API container remains mounted read-only.

- [ ] **Step 3: Validate final bytes before indexing**

In a read-only one-shot container call `load_report_manifest` and require:

```text
theme_id = ai_power_value_capture_v1
version = 2026-08-03.1
title = AI供电产业链分析报告
pdf = null
Markdown SHA-256 equals the manifest value
```

- [ ] **Step 4: Run the authorized indexer twice**

First command:

```bash
python -m stock_research.theme_research_report_index \
  --root /app/reports/theme-research \
  --service theme_research_report_indexer
```

First result must include:

```json
{"discovered": 1, "indexed": 1, "unchanged": 0, "invalid": 0, "errors": []}
```

Run again. Second result must include:

```json
{"discovered": 1, "indexed": 0, "unchanged": 1, "invalid": 0, "errors": []}
```

- [ ] **Step 5: Verify database state and initial audit event**

Query:

```sql
SELECT report_version_id, theme_id, version, title, status, row_version
FROM research.theme_research_report_version
WHERE theme_id = 'ai_power_value_capture_v1'
  AND version = '2026-08-03.1';
```

Expected exactly one row with title `AI供电产业链分析报告`, status `pending_review`, and `row_version=1`.

Query the associated review events. Expected exactly one event with `to_status='pending_review'` and `actor_user_id='system'`.

## Task 8: Verify human-review readiness without publishing

- [ ] **Step 1: Verify the admin queue**

`GET /api/admin/theme-research/reports?status=pending_review` must return exactly one item with:

```text
theme_id = ai_power_value_capture_v1
version = 2026-08-03.1
title = AI供电产业链分析报告
status = pending_review
```

- [ ] **Step 2: Verify the admin document**

Fetch the returned `report_version_id`. Require all fixed report headings, sanitized rendered content, and no absolute server path, checksum field, raw manifest path, or prohibited trading phrase in the API response.

- [ ] **Step 3: Verify approved-user invisibility**

Call `/api/research/theme-decomposition/themes/ai_power_value_capture_v1/reports`. The pending version must be absent even when called with the admin session because this read model selects only `published` and `archived` versions.

If secure non-admin canary credentials already exist, repeat list and direct-document checks with that user and require absence/404. Do not create a production user solely for this check.

- [ ] **Step 4: Inspect the actual admin page**

Open `https://stock.manqiaotechnology.com/admin/theme-research/report-review` with the authenticated admin session and verify:

```text
heading = 主题报告审核
queue title = AI供电产业链分析报告
version = 2026-08-03.1
state = pending_review / 待审核
complete Markdown preview renders
publish and reject controls are visible but untouched
PDF action is absent or disabled
```

Leave the browser on this preview. Do not publish or reject.

- [ ] **Step 5: Run fresh final verification**

Repeat the affected backend tests, frontend build, report E2E, external release gate, database query, admin pending API, and approved-list exclusion. Completion requires fresh zero-exit evidence from every command.

## Task 9: Handoff

- [ ] **Step 1: Record final evidence**

Capture the production release SHA, report version ID, theme/version, manifest validation, first/second scan counts, database status, audit event, admin queue count, approved-list exclusion, and test totals.

- [ ] **Step 2: Report the exact stopping point**

Provide the admin review URL and explicitly state:

```text
The report is ready for human review and remains pending_review.
No approval, rejection, archive, or public publication was performed.
```
