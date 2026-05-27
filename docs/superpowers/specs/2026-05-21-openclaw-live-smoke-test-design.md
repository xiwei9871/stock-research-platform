# OpenClaw Live Smoke Test Design

## Scope

This spec covers the first live-send preparation layer for report delivery:

- an OpenClaw sender module
- transport abstractions
- strict live-send safety guards
- dry-run and mock validation
- documentation for manual real-endpoint smoke testing

This phase does not perform bulk real sending automatically.

## Goals

The sender should:

1. read `openclaw_manifest.json`
2. read `openclaw_items.jsonl`
3. support dry-run by default
4. write a local preview and send log
5. support real HTTP sending only behind explicit guards
6. support mock/fake transport testing without network access
7. keep secrets out of logs and preview artifacts

## Non-Goals

This phase does not:

- send to Feishu
- perform AI reasoning
- alter selection, factor, or backtest logic
- auto-execute a real smoke test
- introduce WebSocket transport
- introduce OpenClaw CLI transport
- allow default bulk live sending

## Audit Findings

Based on repository inspection, the current OpenClaw-related usage is split across two
separate layers:

1. older watchdog/notification code that treats `openclaw` as a CLI tool or external
   integration surface
2. the new report delivery pipeline, which currently has:
   - Local Delivery
   - OpenClaw Export Adapter

There is not enough evidence in the codebase to claim that a stable real OpenClaw HTTP
gateway contract is already in use by report delivery.

Therefore:

- this phase keeps the sender transport generic
- dry-run and mock validation are first-class
- real live sending remains manual and guarded

## Transport Decision

Keep exactly three transport types:

- `DryRunOpenClawTransport`
- `FakeOpenClawTransport`
- `HttpOpenClawTransport`

Do not add:

- WebSocket transport
- OpenClaw CLI transport

If a real endpoint later proves not to be compatible with the HTTP sender, the next phase
can add a new transport. This phase should not guess the live protocol.

## Module Boundary

Create a dedicated sender module:

- `src/stock_research/report_delivery_openclaw_sender.py`

Keep export and sending separate:

- `report_delivery_openclaw.py` stays export-only
- `report_delivery_openclaw_sender.py` owns send config, transport, guardrails, preview,
  and send logging

## Core Types

### `OpenClawSendConfig`

The config should contain:

- `endpoint`
- `token`
- `timeout_seconds`
- `dry_run`
- `retry_count`
- `retry_backoff_seconds`
- `outbox_dir`
- `limit`
- `allow_live_send`
- `route_allowlist`
- `severity_max`
- `test_mode`

### `OpenClawSendResult`

The result should contain:

- `send_id`
- `channel`
- `status`
- `dry_run`
- `item_count`
- `sent_count`
- `failed_count`
- `skipped_count`
- `preview_path`
- `send_log_path`
- `errors`
- `warnings`
- `generated_at`

### `OpenClawSender`

The sender should expose:

- `load_export(...)`
- `build_send_payload(...)`
- `send_item(...)`
- `send_batch(...)`
- `write_send_preview(...)`
- `write_send_log(...)`

## Configuration Sources

Configuration priority:

1. CLI arguments
2. environment variables
3. defaults

Supported environment variables:

- `OPENCLAW_ENDPOINT`
- `OPENCLAW_TOKEN`
- `OPENCLAW_TIMEOUT_SECONDS`

Rules:

- `endpoint` is optional in dry-run
- `endpoint` is mandatory for real sending
- token may be absent
- token must never be printed to stdout
- token must never be written to preview or log files

## Input and Output

### Inputs

- `openclaw_manifest.json`
- `openclaw_items.jsonl`

### Output Directory

Recommended output root:

- `outputs/report_delivery/openclaw_send/YYYY-MM-DD/`

### `send_preview.json`

Must contain:

- `generated_at`
- `dry_run`
- `source_openclaw_manifest_path`
- `item_count`
- `payloads`
- `warnings`
- `errors`

### `send_log.jsonl`

Each line must contain at least:

- `send_id`
- `item_id`
- `artifact_id`
- `report_type`
- `openclaw_route`
- `status`
- `dry_run`
- `endpoint_host`
- `error_message`
- `sent_at`

Restrictions:

- never record token
- never record auth headers
- logging the endpoint host is allowed

## Payload Shape

The sender should emit a transport-level payload like:

```json
{
  "route": "...",
  "action": "...",
  "title": "...",
  "summary": "...",
  "severity": "...",
  "tags": ["..."],
  "payload": { ... }
}
```

`payload` should contain at least:

- `title`
- `summary`
- `severity`
- `report_type`
- `tags`
- `source_paths`
- `evidence_paths`
- `metadata`
- `warnings`

If `test_mode` is enabled, inject into payload metadata:

- `test_mode: true`
- `source: stock_research_openclaw_smoke_test`

This phase must not add advisory text or trading conclusions.

## Dry-Run Behavior

Dry-run is the default.

In dry-run mode:

- do not access network
- do not require endpoint
- do not require token
- still write `send_preview.json`
- still write `send_log.jsonl`
- write `status=dry_run` for each log row

This mode should be fully auditable and deterministic.

## Real Send Behavior

Real sending is allowed only with explicit opt-in.

`--no-dry-run` alone is not enough.

The sender must reject real sending unless all of the following are true:

- `--no-dry-run`
- `--allow-live-send`
- endpoint is present from CLI or environment
- `--limit 1`
- `--route-allowlist` is provided and permits the item route
- `--severity-max` is provided and the item severity is within limit
- `--test-mode` is enabled

This is intentionally stricter than the eventual production sender.

## Safety Guards

### `--limit`

For live sending:

- must be explicitly present
- must equal `1`

This phase does not allow multi-item real sends.

### `--allow-live-send`

Required for any non-dry-run send.

Without it, the sender should refuse real network access even if `--no-dry-run` is set.

### `--route-allowlist`

Allows only whitelisted routes during live sending.

This phase expects low-risk routes such as:

- `research_inbox`
- `evidence_review`

### `--severity-max`

For smoke tests, use to cap live sends to low-risk items.

This phase expects smoke tests to stay within:

- `info`
- `low`

### `--test-mode`

Required for live smoke tests.

This marks payloads so the receiving side can identify them as explicit smoke-test
traffic.

## Error Handling

The sender must fail clearly when:

- export manifest is missing
- export items file is missing
- real send is requested without endpoint
- real send is requested without `--allow-live-send`
- real send is requested without `--limit 1`
- real send is requested without route allowlist
- real send is requested without severity cap
- real send is requested without test mode

Batch semantics:

- one item failure must not stop the remaining items
- failures must increment `failed_count`
- all item outcomes must be logged

## Mock Endpoint Validation

Before any real endpoint use, this phase should validate the sender with local test
transports.

Accepted approaches:

- `FakeOpenClawTransport`
- monkeypatched HTTP transport
- lightweight local HTTP server if convenient

Requirements:

- no dependency on a running real OpenClaw service
- payload capture for assertion
- success and partial-failure coverage

## Real Smoke Test Command Template

Do not auto-run this command in the implementation.

Reference command:

```bash
stock-research report-delivery-openclaw-send \
  --trade-date 2026-05-20 \
  --manifest outputs/report_delivery/openclaw/2026-05-20/openclaw_manifest.json \
  --items outputs/report_delivery/openclaw/2026-05-20/openclaw_items.jsonl \
  --output-dir outputs/report_delivery/openclaw_send/2026-05-20 \
  --endpoint "$OPENCLAW_ENDPOINT" \
  --no-dry-run \
  --allow-live-send \
  --limit 1 \
  --route-allowlist research_inbox \
  --severity-max low \
  --test-mode
```

This is documentation and operator guidance only.

## CLI

Add a new command:

```bash
stock-research report-delivery-openclaw-send \
  --trade-date 2026-05-20 \
  --manifest outputs/report_delivery/openclaw/2026-05-20/openclaw_manifest.json \
  --items outputs/report_delivery/openclaw/2026-05-20/openclaw_items.jsonl \
  --output-dir outputs/report_delivery/openclaw_send/2026-05-20 \
  --dry-run
```

Supported flags:

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

## Testing

Add or extend:

- `tests/test_report_delivery_openclaw_sender.py`

At minimum cover:

1. dry-run does not access network
2. dry-run writes `send_preview.json`
3. dry-run writes `send_log.jsonl`
4. no-dry-run without endpoint fails clearly
5. no-dry-run without `--allow-live-send` fails clearly
6. `--limit` constrains sent items
7. route allowlist filters items
8. severity max filters items
9. test mode marks payload metadata
10. token does not appear in logs
11. fake transport can simulate success
12. fake transport can simulate partial failure
13. sent/failed/skipped counts are correct
14. missing manifest or items file fails clearly
15. empty items do not crash and produce warnings
16. no real external access in test mode

If CLI tests live in `tests/test_factor_cli.py`, add focused command coverage there.

## Documentation Update

Append an `OpenClaw Sender v0` section to:

- `docs/quant_system/12_p1_report_delivery_adapter_plan.md`

It should cover:

1. relation to OpenClaw Export Adapter
2. default dry-run
3. `send_preview.json`
4. `send_log.jsonl`
5. environment variables
6. CLI example
7. real-send safety conditions
8. token never enters logs
9. relation to future Feishu Adapter

## Scope Discipline

This phase must not:

- auto-run a live send
- send to Feishu
- add AI reasoning
- add trading actions
- loosen the live-send guardrails
