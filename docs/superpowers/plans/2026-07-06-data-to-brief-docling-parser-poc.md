# Data-to-Brief Docling Parser PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated Docling parser PoC that converts locally available pilot-stock PDFs into structured chunks and evidence-ready manifests without changing production strategy, scoring, or dashboard logic.

**Architecture:** Add a small optional adapter module under `src/stock_research/` and a script under `scripts/`. The adapter discovers local PDFs for the five pilot stocks, runs `pypdf` baseline extraction and optional Docling conversion, then writes deterministic CSV/JSON/Markdown artifacts under `outputs/research/data_to_brief_docling_parser_poc_v1/`.

**Tech Stack:** Python 3.11, pandas, pypdf, optional Docling runtime import, pytest.

---

### Task 1: Plan and Output Contract

**Files:**
- Create: `docs/superpowers/plans/2026-07-06-data-to-brief-docling-parser-poc.md`

- [x] **Step 1: Define PoC scope**

Keep this run limited to:
- pilot stocks: `002371`, `688012`, `002885`, `300838`, `000400`
- local PDF discovery under `data/manual`
- parser comparison and evidence-ready outputs
- no DB writes
- no production signal, admission, or scoring changes

- [x] **Step 2: Define required output files**

The run must write:
- `docling_install_smoke.json`
- `parser_comparison_matrix.csv`
- `parsed_documents/`
- `chunks/`
- `table_inventory.csv`
- `source_chunk_manifest.csv`
- `pilot_evidence_matrix.csv`
- `pilot_claim_citation_map.csv`
- `pilot_run_summary.json`

### Task 2: Failing Tests

**Files:**
- Create: `tests/test_data_to_brief_docling_parser_poc.py`

- [ ] **Step 1: Test optional parser output contract**

Write tests that call `run_data_to_brief_docling_parser_poc(...)` with a tiny local fake PDF path and a fake Docling parser callable. Assert all required files exist, missing-stock rows are recorded as `evidence_required`, parsed documents/chunks are written, and every pilot evidence claim maps to a citation.

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_data_to_brief_docling_parser_poc.py -q
```

Expected: fail because `stock_research.data_to_brief_docling_parser_poc` does not exist.

### Task 3: Adapter Module

**Files:**
- Create: `src/stock_research/data_to_brief_docling_parser_poc.py`

- [ ] **Step 1: Implement pilot source discovery**

Implement fixed pilot stock metadata, local PDF discovery by stock code or stock name, and an explicit `evidence_required` row when no PDF is found.

- [ ] **Step 2: Implement optional Docling conversion**

Implement `parse_with_docling(pdf_path)` with runtime import:

```python
from docling.document_converter import DocumentConverter
```

Return a structured status dict. If Docling is unavailable or conversion fails, return status and error text instead of raising.

- [ ] **Step 3: Implement deterministic output writer**

Write parser comparison rows, source chunk rows, evidence matrix, claim-citation map, table inventory, per-document Markdown/JSON, and summary JSON.

- [ ] **Step 4: Run focused tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_data_to_brief_docling_parser_poc.py -q
```

Expected: pass.

### Task 4: Runner Script

**Files:**
- Create: `scripts/run_data_to_brief_docling_parser_poc.py`

- [ ] **Step 1: Add script entrypoint**

The script calls the adapter with default output:

```text
outputs/research/data_to_brief_docling_parser_poc_v1/
```

It accepts:
- `--output-dir`
- `--source-root`
- `--limit-per-stock`

- [ ] **Step 2: Test script invocation**

Run:

```bash
rtk .venv/bin/python scripts/run_data_to_brief_docling_parser_poc.py --limit-per-stock 1
```

Expected: prints summary and artifact paths.

### Task 5: Local Docling Smoke

**Files:**
- Modify only virtualenv state if needed; do not make Docling a mandatory project dependency.

- [ ] **Step 1: Check local install**

Run:

```bash
rtk .venv/bin/python -c "import docling; print(getattr(docling, '__version__', 'unknown'))"
```

- [ ] **Step 2: Install if missing**

Run only if missing:

```bash
rtk .venv/bin/python -m pip install docling
```

- [ ] **Step 3: Run PoC with real local PDFs**

Run:

```bash
rtk .venv/bin/python scripts/run_data_to_brief_docling_parser_poc.py --limit-per-stock 1
```

Expected: local PDFs parse where available, missing pilot stocks remain `evidence_required`, and `docling_install_smoke.json` records actual runtime state.

### Task 6: Verification

**Files:**
- Test: `tests/test_data_to_brief_docling_parser_poc.py`

- [ ] **Step 1: Run focused tests**

```bash
rtk .venv/bin/pytest tests/test_data_to_brief_docling_parser_poc.py -q
```

- [ ] **Step 2: Inspect output summary**

```bash
rtk .venv/bin/python - <<'PY'
import json
from pathlib import Path
path = Path("outputs/research/data_to_brief_docling_parser_poc_v1/pilot_run_summary.json")
print(json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
PY
```

- [ ] **Step 3: Confirm no production logic changed**

Run:

```bash
rtk git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py
```

Expected: empty diff.
