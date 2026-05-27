# OpenClaw Live Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a guarded OpenClaw sender layer that supports dry-run previews, mock/fake transport testing, and tightly constrained manual HTTP live smoke testing without altering research logic.

**Architecture:** Keep export and sending separate by introducing a dedicated sender module that consumes `openclaw_manifest.json` and `openclaw_items.jsonl`. The sender will select a transport (`DryRun`, `Fake`, or `HTTP`), enforce live-send guardrails before any network access, and always emit `send_preview.json` and `send_log.jsonl` for auditing.

**Tech Stack:** Python 3, dataclasses, pathlib, json, urllib/http client or existing standard library HTTP primitives, pytest, existing stock_research CLI

---

## File Map

- Create: `src/stock_research/report_delivery_openclaw_sender.py`
  - Sender config/result types, transports, guardrails, preview/log writing
- Modify: `src/stock_research/cli.py`
  - Add `report-delivery-openclaw-send`
- Create: `tests/test_report_delivery_openclaw_sender.py`
  - Sender tests, fake transport, dry-run and guardrail coverage
- Modify: `tests/test_factor_cli.py`
  - Focused CLI coverage for the new command
- Modify: `docs/quant_system/12_p1_report_delivery_adapter_plan.md`
  - Append `OpenClaw Sender v0`

## Task 1: Define Sender Contract and Dry-Run Skeleton

**Files:**
- Create: `src/stock_research/report_delivery_openclaw_sender.py`
- Create: `tests/test_report_delivery_openclaw_sender.py`

- [ ] **Step 1: Write the failing sender contract tests**

```python
def test_openclaw_sender_dry_run_writes_preview_and_log(tmp_path):
    manifest_path = tmp_path / "openclaw_manifest.json"
    items_path = tmp_path / "openclaw_items.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-05-21T09:00:00Z",
                "trade_date": "2026-05-20",
                "channel": "openclaw",
                "dry_run": True,
                "source_manifest_path": "outputs/report_delivery/2026-05-20/manifest.json",
                "item_count": 1,
                "items": [],
                "warnings": [],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    items_path.write_text(
        json.dumps(
            {
                "item_id": "openclaw:1",
                "artifact_id": "daily_topn_report:2026-05-20:abc",
                "report_type": "daily_topn_report",
                "title": "Daily TopN",
                "summary": "Daily TopN summary",
                "severity": "info",
                "requires_attention": False,
                "delivery_priority": 10,
                "tags": ["daily", "topn"],
                "source_paths": ["outputs/report_delivery/2026-05-20/artifacts/topn.md"],
                "evidence_paths": [],
                "run_card_path": None,
                "recommended_action": "review_topn_candidates",
                "openclaw_route": "daily_research",
                "payload": {"title": "Daily TopN"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint=None,
        token=None,
        timeout_seconds=5,
        dry_run=True,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=None,
        allow_live_send=False,
        route_allowlist=[],
        severity_max=None,
        test_mode=False,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.DryRunOpenClawTransport()
    )

    result = sender.send_batch(
        manifest_path=manifest_path,
        items_path=items_path,
        config=config,
    )

    assert result.dry_run is True
    assert result.item_count == 1
    assert result.sent_count == 0
    assert result.failed_count == 0
    assert result.skipped_count == 0
    assert Path(result.preview_path).exists()
    assert Path(result.send_log_path).exists()
```

```python
def test_openclaw_sender_no_dry_run_without_endpoint_fails_clearly(tmp_path):
    ...
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw_sender.py -q
```

Expected:

- FAIL because the sender module does not yet exist

- [ ] **Step 3: Add sender types and dry-run skeleton**

Create `src/stock_research/report_delivery_openclaw_sender.py` with:

```python
@dataclass(frozen=True)
class OpenClawSendConfig:
    endpoint: str | None
    token: str | None
    timeout_seconds: float
    dry_run: bool
    retry_count: int
    retry_backoff_seconds: float
    outbox_dir: str
    limit: int | None
    allow_live_send: bool
    route_allowlist: list[str]
    severity_max: str | None
    test_mode: bool


@dataclass(frozen=True)
class OpenClawSendResult:
    send_id: str
    channel: str
    status: str
    dry_run: bool
    item_count: int
    sent_count: int
    failed_count: int
    skipped_count: int
    preview_path: str
    send_log_path: str
    errors: list[str]
    warnings: list[str]
    generated_at: str
```

Add:

- `DryRunOpenClawTransport`
- `FakeOpenClawTransport`
- placeholder `HttpOpenClawTransport`
- `OpenClawSender.load_export(...)`
- `OpenClawSender.build_send_payload(...)`
- `OpenClawSender.send_batch(...)`
- `OpenClawSender.write_send_preview(...)`
- `OpenClawSender.write_send_log(...)`

The skeleton should:

- read export files
- write preview/log
- never access network in dry-run

- [ ] **Step 4: Run the targeted tests to confirm pass**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw_sender.py -q
```

Expected:

- PASS for the initial dry-run and endpoint guard tests

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery_openclaw_sender.py tests/test_report_delivery_openclaw_sender.py
git commit -m "feat: add openclaw sender skeleton"
```

## Task 2: Implement Live-Send Guardrails and Filtering

**Files:**
- Modify: `src/stock_research/report_delivery_openclaw_sender.py`
- Modify: `tests/test_report_delivery_openclaw_sender.py`

- [ ] **Step 1: Write failing guardrail and filtering tests**

```python
def test_live_send_requires_allow_live_send(tmp_path):
    ...

def test_live_send_requires_limit_one(tmp_path):
    ...

def test_route_allowlist_filters_items(tmp_path):
    ...

def test_severity_max_filters_items(tmp_path):
    ...

def test_test_mode_marks_payload_metadata(tmp_path):
    ...
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw_sender.py -q -k "allow_live_send or limit_one or route_allowlist or severity_max or test_mode"
```

Expected:

- FAIL before the guardrails are implemented

- [ ] **Step 3: Implement live-send gate validation**

Add sender-side validation so real sending is rejected unless all are true:

- `dry_run` is false
- `allow_live_send` is true
- endpoint exists
- `limit == 1`
- route allowlist is non-empty
- severity max is present
- test mode is true

Add item filtering logic for:

- `limit`
- `route_allowlist`
- `severity_max`

Add payload metadata for test mode:

```python
payload["payload"]["metadata"]["test_mode"] = True
payload["payload"]["metadata"]["source"] = "stock_research_openclaw_smoke_test"
```

- [ ] **Step 4: Run the targeted tests to confirm pass**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw_sender.py -q -k "allow_live_send or limit_one or route_allowlist or severity_max or test_mode"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery_openclaw_sender.py tests/test_report_delivery_openclaw_sender.py
git commit -m "feat: add openclaw live-send guardrails"
```

## Task 3: Fake/HTTP Transport Behavior and Logging Hygiene

**Files:**
- Modify: `src/stock_research/report_delivery_openclaw_sender.py`
- Modify: `tests/test_report_delivery_openclaw_sender.py`

- [ ] **Step 1: Write failing transport and logging tests**

```python
def test_fake_transport_can_simulate_success(tmp_path):
    ...

def test_fake_transport_can_simulate_partial_failure(tmp_path):
    ...

def test_token_never_appears_in_send_log(tmp_path):
    ...

def test_dry_run_transport_never_accesses_network(tmp_path, monkeypatch):
    ...
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw_sender.py -q -k "fake_transport or token_never_appears or dry_run_transport"
```

Expected:

- FAIL before transport behavior and log hygiene are complete

- [ ] **Step 3: Implement fake transport, HTTP transport shell, and safe logs**

Requirements:

- `FakeOpenClawTransport` can simulate per-item success or failure
- `DryRunOpenClawTransport` records dry-run without network
- `HttpOpenClawTransport` builds HTTP POST payloads but is only used in non-dry-run
- `send_log.jsonl` records only endpoint host, never token

Keep token handling local to transport request construction. Never serialize it into:

- preview JSON
- send log JSONL
- stdout

- [ ] **Step 4: Run the targeted tests to confirm pass**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw_sender.py -q -k "fake_transport or token_never_appears or dry_run_transport"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery_openclaw_sender.py tests/test_report_delivery_openclaw_sender.py
git commit -m "fix: harden openclaw sender transport logging"
```

## Task 4: CLI Wiring and Plan Doc Update

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `docs/quant_system/12_p1_report_delivery_adapter_plan.md`
- Modify: `src/stock_research/report_delivery_openclaw_sender.py` only if CLI exposes a real bug

- [ ] **Step 1: Write failing CLI tests**

```python
def test_cli_accepts_report_delivery_openclaw_send_command():
    ...

def test_openclaw_send_cli_dry_run_invokes_sender(monkeypatch, capsys):
    ...

def test_openclaw_send_cli_no_dry_run_without_endpoint_fails(monkeypatch):
    ...
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery"
```

Expected:

- FAIL until the new sender command is wired in

- [ ] **Step 3: Wire the CLI and update docs**

Add command:

```bash
report-delivery-openclaw-send
```

Arguments:

- `--trade-date`
- `--manifest`
- `--items`
- `--output-dir`
- `--dry-run`
- `--no-dry-run`
- `--endpoint`
- `--timeout-seconds`
- `--retry-count`
- `--retry-backoff-seconds`
- `--allow-live-send`
- `--limit`
- `--route-allowlist`
- `--severity-max`
- `--test-mode`

Append `OpenClaw Sender v0` to the plan doc, covering:

- relation to export adapter
- dry-run default
- `send_preview.json`
- `send_log.jsonl`
- environment variables
- CLI example
- safety conditions for real send
- token not in logs
- relation to future Feishu adapter

- [ ] **Step 4: Run focused verification**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw_sender.py -q
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py docs/quant_system/12_p1_report_delivery_adapter_plan.md src/stock_research/report_delivery_openclaw_sender.py
git commit -m "feat: add openclaw sender cli"
```

## Task 5: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run sender and related report delivery tests**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q
.venv/bin/pytest tests/test_report_delivery_openclaw_sender.py -q
```

Expected:

- PASS

- [ ] **Step 2: Run CLI regression tests**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery"
```

Expected:

- PASS

- [ ] **Step 3: Inspect worktree state**

Run:

```bash
git status --short
```

Expected:

- only intended tracked sender changes
- ignore unrelated untracked `docs/superpowers/*` notes

- [ ] **Step 4: Prepare handoff summary**

Summarize:

- audit findings about current OpenClaw entry/protocol
- HTTP transport fit and remaining unknowns
- new safety parameters
- dry-run / fake / live smoke order
- smoke-test command template
- test results
- confirmation that no real OpenClaw access occurred

No commit in this task. Use the summary for final user-facing closeout after implementation.

## Self-Review

- Spec coverage:
  - sender module and transports: Task 1 and Task 3
  - live guardrails: Task 2
  - preview/log outputs: Task 1 and Task 3
  - CLI and docs: Task 4
  - final validation: Task 5
- Placeholder scan:
  - no TODO/TBD placeholders remain
- Type consistency:
  - sender config/result names are consistent across tasks
  - `test_mode`, `limit`, `route_allowlist`, and `severity_max` are used consistently
