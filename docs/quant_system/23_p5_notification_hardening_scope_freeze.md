# P5 Notification Hardening Scope Freeze

Date: 2026-05-29

## Status

P5 scope is frozen around **Notification Hardening For Scheduled Operations**.

P5 starts after:

- P4 completion review:
  - `docs/quant_system/22_p4_completion_review.md`
- P4 scheduler runbook:
  - `docs/quant_system/21_p4_scheduler_runbook.md`
- P1 report delivery adapter:
  - `docs/quant_system/13_p1_completion_review.md`

## Why This Scope

P4 made the daily P3 import, operator export, read-model freshness smoke, and
scheduler wrapper repeatable. The remaining operational gap is delivery: an
operator still needs to inspect logs manually to know whether a scheduled smoke
passed, warned, or blocked.

P5 therefore hardens notification around P4 smoke output before any dashboard UI.
The goal is not to add a new messaging product. The goal is to convert existing
machine-readable operational output into a dry-run-first notification package
that can reuse the existing Feishu delivery safety model.

## P5 In Scope

### P5-1 P4 Smoke Notification Model

Goal: normalize P4 smoke output into a small notification contract.

Deliver:

- Parser/model for `p4-read-model-smoke` machine-readable lines.
- Severity mapping:
  - `pass` -> `ok`
  - `warning` -> `warning`
  - `blocked` -> `critical`
- Summary fields for trade date, blockers, warnings, failed checks, and source
  command.
- Tests for pass, warning, blocked, malformed, and empty smoke output.

Boundary:

- Do not rerun P4 smoke inside the parser.
- Do not infer market freshness beyond the P4 smoke lines.
- Do not persist webhook URLs, tokens, credentials, broker data, or order data.

### P5-2 Dry-Run Notification Artifact

Goal: write reviewable local notification artifacts for P4 smoke results.

Deliver:

- JSON preview artifact for the normalized notification.
- JSONL delivery log artifact.
- Human-readable message text suitable for Feishu/OpenClaw review.
- Output paths under an operator-controlled output directory.
- Tests for artifact shape, deterministic severity mapping, and source command
  traceability.

Boundary:

- Default behavior must be dry-run.
- Writing preview artifacts must not call any external transport.
- No dashboard, database schema, or scheduler installation changes in this task.

### P5-3 Feishu Reuse Adapter

Goal: reuse the existing dry-run-first Feishu safety pattern for P4 operational
notifications.

Deliver:

- Adapter that maps the P5 notification preview into a Feishu text payload.
- Optional live send path only behind explicit safety gates.
- Safety gates aligned with existing P1 Feishu behavior:
  - dry-run by default
  - explicit live-send flag
  - explicit webhook value at send time
  - single-message limit for live smoke sends
  - test-mode support for fake transport tests
- Tests for dry-run no-transport behavior, live-send guardrails, fake transport
  success, and CLI output.

Boundary:

- Do not hard-code or store webhook URLs.
- Do not introduce a new Feishu transport if the existing transport can be
  reused.
- Do not broaden report-delivery severity semantics; P5 severity is operational
  smoke severity only.

### P5-4 Scheduler Wrapper Notification Hook

Goal: make notification optional and scheduler-safe after P4 smoke.

Deliver:

- CLI command that reads P4 smoke output or a saved smoke log and writes/sends the
  P5 notification.
- Optional wrapper environment switches:
  - notification disabled by default
  - dry-run notification enabled for smoke validation
  - live send only with explicit operator-provided webhook and safety flags
- Machine-readable CLI lines for runbooks.
- Tests for disabled notification, dry-run notification, live guardrails, and
  blocked smoke escalation.

Boundary:

- Do not auto-enable notifications in the scheduler wrapper.
- Do not install cron, launchd, webhooks, or cloud schedulers.
- Do not send notifications for unrelated commands.

### P5-5 Notification Runbook And Completion Review

Goal: document the operational notification flow and review P5 against its
acceptance criteria.

Deliver:

- P5 runbook covering:
  - prerequisites
  - dry-run notification
  - live-send safety gates
  - pass/warning/blocked examples
  - failed notification triage
  - manual rerun steps
- P5 completion review covering:
  - delivered commands
  - artifact contract
  - safety review
  - verification evidence

Boundary:

- Do not move dashboard UI into P5.
- Do not expand P5 into alert policy tuning beyond the three P4 smoke statuses.

## Out Of Scope For P5

- Dashboard UI or dashboard backend.
- Broker adapters.
- Live trading.
- Automatic order placement.
- Order, execution, account, cash, or position ledger tables.
- New scheduler daemon, queue, cloud worker, or cron auto-installation.
- Replacing P4 smoke checks.
- Rewriting report delivery adapters.
- Alpha191 pilot validation or factor formula work.
- Persisting credentials, tokens, webhook URLs, broker account data, or order
  payloads.

## Execution Order

1. P5-0: preserve workspace boundary and leave Alpha191/dashboard workbench files
   untouched unless explicitly requested.
2. P5-1: add P4 smoke notification model and severity mapping.
3. P5-2: add dry-run notification preview/log artifacts.
4. P5-3: add Feishu reuse adapter and safety gates.
5. P5-4: add optional scheduler wrapper notification hook.
6. P5-5: write runbook and completion review.

## Acceptance Criteria

P5 is ready for review when:

- P4 smoke statuses map deterministically to operational notification severity.
- A dry-run notification artifact can be generated without network access.
- Warning and blocked smoke results produce operator-actionable messages.
- Feishu delivery, if added, reuses existing dry-run-first safety behavior.
- Live send requires explicit operator action and never stores secrets.
- Scheduler notification behavior is disabled unless explicitly enabled.
- Notification commands emit machine-readable output for runbooks.
- P5 docs explain dry-run, live-send safety, triage, and rerun steps.
- Alpha191 and dashboard workbench files remain outside the P5 commit set.
- `.venv/bin/pytest -q` passes on a workspace that excludes unrelated Alpha191
  pilot work.

## Safety Rules

- Notification hardening is operational only; it must not create trading actions.
- `blocked` smoke must be treated as critical notification severity, not as a
  reason to trade.
- `warning` smoke must require human review, not automatic suppression.
- All notification outputs must preserve the source smoke status and source
  command or log path.
- Dry-run is the default for every new send-related command.
- No secret may be written to generated previews, logs, docs, or database rows.
- Scheduler notification enablement must remain a manual operator decision.

## First Implementation Target

Start with P5-1 and P5-2 together:

- parse existing `p4-read-model-smoke` output lines
- map the final smoke status to operational severity
- produce a local notification preview and delivery log
- add targeted tests before implementation

After those pass, reuse the P1 Feishu sender pattern for P5-3 instead of
inventing a separate notification transport.
