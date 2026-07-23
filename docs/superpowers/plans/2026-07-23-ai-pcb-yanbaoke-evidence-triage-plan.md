# AI PCB Yanbaoke Evidence Triage v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a deterministic, offline, read-only triage of the 474-report Yanbaoke batch that separates traceable source leads, contextual industry material, future company-evidence leads, and investment opinion from direct technical evidence.

**Architecture:** Add one task-specific Python module containing input validation, relevance selection, content-identity collapse, restricted ER mapping, and deterministic output rendering. A thin script invokes that module against the frozen 2026-07-23 run directory. Focused tests prove that duplicates do not increase evidence counts, prohibited evidence states cannot be emitted, and upstream inputs remain unchanged.

**Tech Stack:** Python 3, pandas, pypdf, hashlib, csv/json, pytest.

---

## File structure

- Create `src/stock_research/ai_pcb_yanbaoke_evidence_triage.py`: task-specific triage rules, input hashing, PDF text extraction, content-identity collapse, classification, ER disposition, validation, and rendering.
- Create `scripts/run_ai_pcb_yanbaoke_evidence_triage.py`: minimal command-line entry point with no network or database dependencies.
- Create `tests/test_ai_pcb_yanbaoke_evidence_triage.py`: focused behavior and fail-closed tests.
- Generate `outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_v1.csv`: selected reports, one row per unique content identity.
- Generate `outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_audit_v1.json`: input hashes, rule version, counts, classifications, ER lead counts, and validation results.
- Generate `outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_summary_v1.md`: deterministic readable projection.

### Task 1: Establish the fail-closed triage contract

**Files:**
- Create: `tests/test_ai_pcb_yanbaoke_evidence_triage.py`
- Create: `src/stock_research/ai_pcb_yanbaoke_evidence_triage.py`

- [ ] **Step 1: Write failing tests for allowed classifications and ER dispositions**

```python
from stock_research.ai_pcb_yanbaoke_evidence_triage import (
    validate_primary_classification,
    validate_er_disposition,
)


def test_rejects_direct_evidence_and_er_sufficiency_states():
    validate_primary_classification("primary_source_lead")
    validate_er_disposition("source_discovery_only")

    with pytest.raises(ValueError, match="unsupported primary classification"):
        validate_primary_classification("direct_evidence")
    with pytest.raises(ValueError, match="unsupported ER disposition"):
        validate_er_disposition("sufficient")
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: collection fails because `stock_research.ai_pcb_yanbaoke_evidence_triage` does not exist.

- [ ] **Step 3: Implement fixed enums and validators**

```python
PRIMARY_CLASSIFICATIONS = frozenset(
    {
        "primary_source_lead",
        "contextual_industry",
        "company_evidence_lead",
        "investment_opinion_non_evidence",
    }
)
ER_DISPOSITIONS = frozenset(
    {"source_discovery_only", "contextual_candidate", "not_relevant"}
)


def validate_primary_classification(value: str) -> None:
    if value not in PRIMARY_CLASSIFICATIONS:
        raise ValueError(f"unsupported primary classification: {value}")


def validate_er_disposition(value: str) -> None:
    if value not in ER_DISPOSITIONS:
        raise ValueError(f"unsupported ER disposition: {value}")
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the contract**

```bash
git add src/stock_research/ai_pcb_yanbaoke_evidence_triage.py tests/test_ai_pcb_yanbaoke_evidence_triage.py
git commit -m "test: define AI PCB evidence triage contract"
```

### Task 2: Load, hash, select, and collapse report identities

**Files:**
- Modify: `src/stock_research/ai_pcb_yanbaoke_evidence_triage.py`
- Modify: `tests/test_ai_pcb_yanbaoke_evidence_triage.py`

- [ ] **Step 1: Write failing tests for strict selection and duplicate collapse**

```python
def test_generic_ai_terms_do_not_select_a_report():
    row = {"report_title": "AI服务器行业更新", "stock_name": "样本公司", "content": "算力需求增长"}
    result = classify_relevance(row, body_text="")
    assert result.selected is False


def test_specific_pcb_material_terms_select_a_report():
    row = {"report_title": "HVLP铜箔与高速覆铜板研究", "stock_name": "样本公司", "content": ""}
    result = classify_relevance(row, body_text="Rz and insertion loss are discussed")
    assert result.selected is True
    assert "copper_foil" in result.relevance_domains


def test_same_content_hash_collapses_to_one_document_identity():
    rows = [
        {"uuid": "u1", "content_sha256": "abc", "report_title": "Report A"},
        {"uuid": "u2", "content_sha256": "abc", "report_title": "Report A mirror"},
    ]
    identities = collapse_content_identities(rows)
    assert len(identities) == 1
    assert identities[0]["source_record_uuids"] == ["u1", "u2"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: FAIL because relevance classification and identity collapse are missing.

- [ ] **Step 3: Implement input hashing, PDF extraction, relevance rules, and identity collapse**

Implement these interfaces:

```python
@dataclass(frozen=True)
class RelevanceResult:
    selected: bool
    relevance_domains: Sequence[str]
    matched_signals: Sequence[str]


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_text(path: Path, *, max_pages: int | None = None) -> tuple[str, str]:
    try:
        reader = PdfReader(path)
        pages = reader.pages if max_pages is None else reader.pages[:max_pages]
        text = "\n".join(page.extract_text() or "" for page in pages).strip()
        return text, "readable" if text else "empty_text"
    except Exception as exc:
        return "", f"unreadable:{type(exc).__name__}"


def classify_relevance(row: Mapping[str, object], *, body_text: str) -> RelevanceResult:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ("report_title", "title", "stock_name", "themes", "content")
    ) + " " + body_text
    matches = {
        domain: tuple(signal for signal in signals if signal.casefold() in haystack.casefold())
        for domain, signals in DOMAIN_SIGNALS.items()
    }
    domains = tuple(sorted(domain for domain, signals in matches.items() if signals))
    signals = tuple(sorted({signal for domain in domains for signal in matches[domain]}))
    return RelevanceResult(bool(domains), domains, signals)


def collapse_content_identities(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        identity = str(row.get("content_sha256") or row.get("uuid") or "")
        grouped.setdefault(identity, []).append(row)
    collapsed = []
    for identity, members in sorted(grouped.items()):
        canonical = dict(members[0])
        canonical["content_identity"] = identity
        canonical["source_record_uuids"] = sorted(str(item.get("uuid") or "") for item in members)
        canonical["duplicate_record_count"] = len(members) - 1
        collapsed.append(canonical)
    return collapsed
```

Use specific domain signals for PCB/HDI/mSAP/substrate, laminate/Dk/Df/resin, copper foil/HVLP/VLP/RTF/Rz/Ra/Rq/RMS, and manufacturing/test processes. Generic AI/server/network terms must never be sufficient without a domain signal.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit selection and identity governance**

```bash
git add src/stock_research/ai_pcb_yanbaoke_evidence_triage.py tests/test_ai_pcb_yanbaoke_evidence_triage.py
git commit -m "feat: select and deduplicate AI PCB report leads"
```

### Task 3: Classify evidence utility and map only permitted ER leads

**Files:**
- Modify: `src/stock_research/ai_pcb_yanbaoke_evidence_triage.py`
- Modify: `tests/test_ai_pcb_yanbaoke_evidence_triage.py`

- [ ] **Step 1: Write failing tests for source-lead, contextual, company-lead, and investment-opinion handling**

```python
def test_traceable_standard_or_paper_reference_becomes_source_lead():
    result = classify_utility(
        title="高速材料研究",
        body_text="数据来源：IPC-TM-650；参见 DOI:10.1234/example",
    )
    assert result.primary_classification == "primary_source_lead"
    assert result.traceable_source_types == ("doi", "standard_number")


def test_investment_recommendation_is_not_technical_evidence():
    result = classify_utility(
        title="公司深度：首次覆盖给予买入评级",
        body_text="目标价和盈利预测显示公司确定受益",
    )
    assert result.primary_classification == "investment_opinion_non_evidence"


def test_a04_requires_measurement_method_terms():
    mappings = map_er_dispositions("插损提高", body_text="高速传输需求增长")
    assert mappings["PCB-ER-A04"] == "not_relevant"

    mappings = map_er_dispositions(
        "S参数测量",
        body_text="fixture removal, de-embedding, reference plane and test coupon",
    )
    assert mappings["PCB-ER-A04"] == "source_discovery_only"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: FAIL because utility classification and ER mapping are missing.

- [ ] **Step 3: Implement classification and restricted ER mapping**

Implement:

```python
@dataclass(frozen=True)
class UtilityResult:
    primary_classification: str
    traceable_source_types: Sequence[str]
    traceable_source_leads: Sequence[str]
    classification_reason: str
    prohibited_use: str


def classify_utility(*, title: str, body_text: str) -> UtilityResult:
    text = f"{title}\n{body_text}"
    doi_leads = tuple(sorted(set(re.findall(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I))))
    standard_leads = tuple(sorted(set(re.findall(r"(?:IPC|IEEE|OIF|PCIe?)[-\s][A-Z0-9.\-/]+", text, re.I))))
    source_types = tuple(name for name, leads in (("doi", doi_leads), ("standard_number", standard_leads)) if leads)
    leads = doi_leads + standard_leads
    investment = any(term in text for term in ("买入评级", "目标价", "盈利预测", "投资建议", "确定受益"))
    company_specific = any(term in text for term in ("公司公告", "年报", "客户认证", "产能", "收入"))
    if investment and not leads:
        primary = "investment_opinion_non_evidence"
    elif leads:
        primary = "primary_source_lead"
    elif company_specific:
        primary = "company_evidence_lead"
    else:
        primary = "contextual_industry"
    return UtilityResult(
        primary_classification=primary,
        traceable_source_types=source_types,
        traceable_source_leads=leads,
        classification_reason=f"deterministic_rule:{primary}",
        prohibited_use="not_direct_evidence;not_er_sufficiency;not_investment_conclusion",
    )


def map_er_dispositions(title: str, *, body_text: str) -> dict[str, str]:
    text = f"{title}\n{body_text}".casefold()
    mappings = {}
    for er_id, rule in ER_SIGNAL_RULES.items():
        object_match = any(term.casefold() in text for term in rule["objects"])
        denominator_match = any(term.casefold() in text for term in rule["denominators"])
        mappings[er_id] = (
            "source_discovery_only" if object_match and denominator_match
            else "contextual_candidate" if object_match
            else "not_relevant"
        )
    return mappings
```

The ER mapper uses denominator-aware signals:

- A02: rate/baud/frequency plus distance/topology/channel composition or measured channel metric;
- A04: S-parameter/insertion-loss measurement plus fixture, de-embedding, reference plane, coupon, or uncertainty method;
- B01: Dk/Df plus named test method, frequency, sample geometry, direction, resin content, or temperature/humidity condition;
- B02: copper profile/roughness/treatment plus Rz/Ra/Rq/RMS, frequency, geometry, VNA, simulation, or measured loss.

Reports can only become `source_discovery_only` or `contextual_candidate`; no path emits a direct-evidence state.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit classification behavior**

```bash
git add src/stock_research/ai_pcb_yanbaoke_evidence_triage.py tests/test_ai_pcb_yanbaoke_evidence_triage.py
git commit -m "feat: classify Yanbaoke evidence utility"
```

### Task 4: Render deterministic audit outputs

**Files:**
- Modify: `src/stock_research/ai_pcb_yanbaoke_evidence_triage.py`
- Create: `scripts/run_ai_pcb_yanbaoke_evidence_triage.py`
- Modify: `tests/test_ai_pcb_yanbaoke_evidence_triage.py`

- [ ] **Step 1: Write failing end-to-end fixture test**

```python
def test_run_triage_writes_reconciled_outputs_without_mutating_inputs(tmp_path):
    input_dir = build_fixture_run_directory(tmp_path)
    before = snapshot_hashes(input_dir)

    result = run_triage(input_dir=input_dir, output_dir=input_dir)

    assert result.queue_rows_considered == 3
    assert result.selected_content_identities == 1
    assert snapshot_input_hashes(input_dir) == before
    assert (input_dir / "ai_pcb_evidence_triage_v1.csv").exists()
    audit = json.loads((input_dir / "ai_pcb_evidence_triage_audit_v1.json").read_text())
    assert audit["validation"]["counts_reconciled"] is True
    assert audit["evidence_assessment_updated"] is False
    assert audit["network_access_used"] is False
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: FAIL because orchestration and rendering are missing.

- [ ] **Step 3: Implement orchestration and renderers**

Implement:

```python
@dataclass(frozen=True)
class TriageRunResult:
    queue_rows_considered: int
    selected_source_records: int
    selected_content_identities: int
    duplicate_source_records: int
    output_paths: Sequence[Path]


def render_summary(audit: Mapping[str, object], selected: pd.DataFrame) -> str:
    classification_counts = selected["primary_classification"].value_counts().sort_index().to_dict()
    lines = [
        "# AI PCB Yanbaoke Evidence Triage v1",
        "",
        f"- Queue rows considered: {audit['queue_rows_considered']}",
        f"- Selected content identities: {audit['selected_content_identities']}",
        f"- Duplicate source records collapsed: {audit['duplicate_source_records']}",
        f"- Primary classifications: {json.dumps(classification_counts, ensure_ascii=False, sort_keys=True)}",
        "- Evidence Assessment updated: no",
        "- Cognition package updated: no",
        "",
        "## Evidence boundary",
        "",
        "All ER mappings are source-discovery or contextual leads. No report is treated as direct technical evidence or as satisfying an ER.",
        "",
    ]
    return "\n".join(lines)


def run_triage(*, input_dir: Path, output_dir: Path) -> TriageRunResult:
    queue_path = input_dir / "yanbaoke_download_queue_474.csv"
    mappings_path = input_dir / "theme_company_mappings.csv"
    manifest_path = input_dir / "download" / "yanbaoke_direct_uuid_downloads.csv"
    input_paths = (queue_path, mappings_path, manifest_path)
    before_hashes = {str(path): sha256_path(path) for path in input_paths}
    queue = pd.read_csv(queue_path, dtype=object).fillna("")
    manifest = pd.read_csv(manifest_path, dtype=object).fillna("")
    if len(queue) != 474:
        raise ValueError(f"expected 474 queue rows, found {len(queue)}")
    downloaded = manifest.loc[manifest["status"].eq("downloaded")].copy()
    rows = build_triage_rows(queue=queue, downloaded=downloaded)
    selected = pd.DataFrame(collapse_content_identities(rows))
    validate_selected_frame(selected)
    audit = build_audit_payload(before_hashes=before_hashes, queue=queue, rows=rows, selected=selected)
    csv_path = output_dir / "ai_pcb_evidence_triage_v1.csv"
    audit_path = output_dir / "ai_pcb_evidence_triage_audit_v1.json"
    summary_path = output_dir / "ai_pcb_evidence_triage_summary_v1.md"
    atomic_write_csv(selected, csv_path)
    atomic_write_text(audit_path, json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_write_text(summary_path, render_summary(audit, selected))
    after_hashes = {str(path): sha256_path(path) for path in input_paths}
    if after_hashes != before_hashes:
        raise RuntimeError("upstream input drift detected")
    return TriageRunResult(
        queue_rows_considered=len(queue),
        selected_source_records=len(rows),
        selected_content_identities=len(selected),
        duplicate_source_records=len(rows) - len(selected),
        output_paths=(csv_path, audit_path, summary_path),
    )
```

The run must:

1. hash the queue, mappings, and download manifest before reading report bodies;
2. verify 474 queue rows and successful-manifest lineage;
3. extract readable PDF text without network access;
4. classify and collapse identities;
5. validate all classifications and ER dispositions;
6. write CSV, JSON, and Markdown atomically;
7. re-hash upstream inputs and fail if any changed;
8. record `evidence_assessment_updated=false`, `cognition_updated=false`, `database_written=false`, and `network_access_used=false`.

Create a thin script:

```python
from pathlib import Path
from stock_research.ai_pcb_yanbaoke_evidence_triage import run_triage


if __name__ == "__main__":
    root = Path("outputs/research/theme_company_yanbaoke_20260723")
    result = run_triage(input_dir=root, output_dir=root)
    print(result)
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit deterministic rendering**

```bash
git add src/stock_research/ai_pcb_yanbaoke_evidence_triage.py scripts/run_ai_pcb_yanbaoke_evidence_triage.py tests/test_ai_pcb_yanbaoke_evidence_triage.py
git commit -m "feat: render AI PCB evidence triage audit"
```

### Task 5: Execute the one-time audit and review selected reports

**Files:**
- Generate: `outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_v1.csv`
- Generate: `outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_audit_v1.json`
- Generate: `outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_summary_v1.md`
- Modify if required by reviewed false positives: `src/stock_research/ai_pcb_yanbaoke_evidence_triage.py`
- Modify if rules change: `tests/test_ai_pcb_yanbaoke_evidence_triage.py`

- [ ] **Step 1: Run the audit against the frozen batch**

Run: `rtk .venv/bin/python scripts/run_ai_pcb_yanbaoke_evidence_triage.py`

Expected: reports 474 queue rows considered, approximately 20–30 selected source records, zero input mutations, and three generated outputs.

- [ ] **Step 2: Review every selected report identity**

For each selected identity, inspect title, extracted passages, source citations, and the local PDF when necessary. Confirm:

- the report is genuinely PCB/material/manufacturing/test relevant;
- its primary classification matches actual content;
- A02/A04/B01/B02 mappings do not exceed `source_discovery_only` or `contextual_candidate`;
- investment recommendations are excluded from evidence use;
- traceable primary-source leads are present in the report rather than inferred by the model.

- [ ] **Step 3: If false positives exist, add a failing regression test before changing rules**

Run the new single test first and confirm the observed report is incorrectly selected or classified. Then make the minimum rule correction and rerun the focused suite.

- [ ] **Step 4: Re-run the audit and validate output reconciliation**

Run:

```bash
rtk .venv/bin/python scripts/run_ai_pcb_yanbaoke_evidence_triage.py
rtk .venv/bin/python -m json.tool outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_audit_v1.json >/dev/null
rtk .venv/bin/python -c "import pandas as pd; p='outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_v1.csv'; f=pd.read_csv(p); assert f['content_identity'].is_unique; print(len(f))"
```

Expected: all commands exit 0; content identities are unique; audit totals equal CSV totals.

- [ ] **Step 5: Commit any reviewed rule changes**

```bash
git add src/stock_research/ai_pcb_yanbaoke_evidence_triage.py tests/test_ai_pcb_yanbaoke_evidence_triage.py
git commit -m "fix: calibrate AI PCB report triage rules"
```

If no reviewed rule changes are needed, do not create an empty commit. The generated output directory is ignored by Git and remains an execution artifact.

### Task 6: Verify scope and regression safety

**Files:**
- Verify only; no intended file changes.

- [ ] **Step 1: Run focused tests**

Run: `rtk .venv/bin/pytest tests/test_ai_pcb_yanbaoke_evidence_triage.py -q`

Expected: PASS.

- [ ] **Step 2: Run related Yanbaoke tests**

Run: `rtk .venv/bin/pytest tests/test_theme_company_yanbaoke_quota.py tests/test_yanbaoke_reports.py -q`

Expected: PASS, or report any pre-existing failure precisely.

- [ ] **Step 3: Validate generated artifacts and upstream hashes**

Run:

```bash
rtk .venv/bin/python -m json.tool outputs/research/theme_company_yanbaoke_20260723/ai_pcb_evidence_triage_audit_v1.json >/dev/null
rtk git diff --check
rtk git status --short
```

Expected: JSON parses, no whitespace errors, and only task files plus pre-existing unrelated user changes appear.

- [ ] **Step 4: Record the final evidence-boundary conclusion**

The handoff must separately state:

- number of selected source records and unique content identities;
- primary classification distribution;
- A02/A04/B01/B02 lead counts by permitted disposition;
- duplicate/common-origin count;
- which reports merit manual original-source resolution;
- why no report was treated as direct evidence or ER sufficiency.
