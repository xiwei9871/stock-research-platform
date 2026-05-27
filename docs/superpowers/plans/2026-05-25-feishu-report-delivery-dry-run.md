# Feishu Report Delivery Dry-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a P1 report-delivery Feishu dry-run adapter that turns local report delivery manifests into reviewable Feishu message previews and delivery logs without sending to external services.

**Architecture:** Reuse the existing local `manifest.json` contract from `report_delivery.py`. Add a focused Feishu adapter module that loads the manifest, selects artifacts, renders compact message cards, writes `feishu_preview.json` and `feishu_delivery_log.jsonl`, and never performs network sends. Wire a CLI command that mirrors the OpenClaw delivery pattern.

**Tech Stack:** Python dataclasses, JSON/JSONL file output, existing `stock_research` CLI, pytest.

---

### Task 1: Feishu Dry-Run Adapter Core

**Files:**
- Create: `src/stock_research/report_delivery_feishu.py`
- Test: `tests/test_report_delivery_feishu.py`

- [ ] **Step 1: Write failing tests**

Cover loading a local manifest, selecting artifacts by severity, rendering Feishu preview items without tokens, and writing a JSONL delivery log.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_report_delivery_feishu.py`

Expected: fail because `stock_research.report_delivery_feishu` does not exist.

- [ ] **Step 3: Implement adapter**

Add `FeishuDryRunAdapter`, `FeishuDeliveryResult`, and `FeishuManifestError`.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/pytest tests/test_report_delivery_feishu.py`

Expected: pass.

### Task 2: CLI Wiring

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Cover parser acceptance and dry-run summary output for `report-delivery-feishu`.

- [ ] **Step 2: Run CLI tests to verify failure**

Run: `.venv/bin/pytest tests/test_factor_cli.py::test_cli_accepts_report_delivery_feishu_command tests/test_factor_cli.py::test_report_delivery_feishu_cli_prints_summary`

Expected: fail because command is not wired.

- [ ] **Step 3: Implement CLI command**

Add parser, import adapter, call dry-run adapter, and print stable summary lines.

- [ ] **Step 4: Run focused CLI tests**

Run: `.venv/bin/pytest tests/test_factor_cli.py::test_cli_accepts_report_delivery_feishu_command tests/test_factor_cli.py::test_report_delivery_feishu_cli_prints_summary`

Expected: pass.

### Task 3: Verification

**Files:**
- No additional files.

- [ ] **Step 1: Run delivery-focused tests**

Run: `.venv/bin/pytest tests/test_report_delivery.py tests/test_report_delivery_openclaw.py tests/test_report_delivery_openclaw_sender.py tests/test_report_delivery_feishu.py`

Expected: pass.

- [ ] **Step 2: Run full regression**

Run: `.venv/bin/pytest`

Expected: pass.
