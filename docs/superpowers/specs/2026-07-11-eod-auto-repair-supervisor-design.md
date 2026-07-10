# EOD Auto Repair Observable Supervisor Design

**Date:** 2026-07-11

**Status:** Approved direction; awaiting written-spec review

## Goal

Prevent OpenClaw from falsely timing out a healthy long-running EOD auto-repair job while preserving detailed local logs, truthful exit status, signal cleanup, and the existing 22:00 schedule and Feishu delivery.

## Root Cause

`scripts/run_platform_ready_check_cron.sh` launches the Python repair process in the background and writes both child output and wrapper heartbeats only to `logs/platform_ready_check.host.log`. OpenClaw therefore receives no stdout while the repair runs. With `noOutputTimeoutSeconds=1200`, a run lasting twenty minutes is terminated even though its local heartbeat is active.

The current wrapper also has no explicit signal-forwarding or heartbeat-process cleanup contract. A supervisor termination can therefore leave child lifecycle and terminal status ambiguous.

## Scope

Modify only the EOD auto-repair wrapper and its focused script tests. Keep the Python repair implementation, repair stages, PostgreSQL data contracts, OpenClaw schedule, Feishu target, and timeout values unchanged.

## Supervisor Contract

The wrapper will:

1. Emit an immediate compact `started` line to stdout before launching the repair child.
2. Keep the child process's complete stdout and stderr in the existing detail log.
3. Emit a compact heartbeat to stdout every `PLATFORM_READY_CHECK_HEARTBEAT_SECONDS`, defaulting to 60 seconds.
4. Include the stage, trade date, elapsed seconds, and latest useful progress line in each heartbeat. If no progress exists, report `waiting`.
5. Forward `SIGTERM` and `SIGINT` to the repair child.
6. Stop and reap the heartbeat process on success, failure, or interruption.
7. Wait for the repair child and preserve its real exit code.
8. Retain the existing compact success/failure summary and detail-log path.

## Process Model

```text
OpenClaw command
  -> wrapper emits started line
  -> wrapper launches Python repair child with output redirected to detail log
  -> wrapper launches heartbeat loop
       -> sleep interruptibly
       -> emit compact heartbeat to stdout
       -> read latest progress marker from detail log
  -> wrapper waits for repair child
  -> signal trap forwards TERM/INT to repair child
  -> wrapper reaps heartbeat process
  -> wrapper prints compact terminal summary
  -> wrapper exits with child exit code
```

The heartbeat loop uses an interruptible background `sleep` so cleanup does not wait for a full heartbeat interval.

## Output Contract

Example stdout:

```text
platform_ready_check|started|stage=eod_auto_repair|trade_date=2026-07-10|detail_log=...
platform_ready_check|heartbeat|stage=eod_auto_repair|trade_date=2026-07-10|elapsed_seconds=60|last_progress=...
EOD自动修复完成
交易日: 2026-07-10
...
```

Verbose Python output remains in `logs/platform_ready_check.host.log` and is not streamed to OpenClaw.

## Error and Signal Handling

- A nonzero Python exit produces the existing failure summary and the same nonzero wrapper exit code.
- `SIGTERM` or `SIGINT` is forwarded to the child; the wrapper then reaps the heartbeat loop and exits nonzero.
- Cleanup is idempotent so normal completion and the `EXIT` trap cannot leave a heartbeat process behind.
- The design does not raise the no-output timeout because observable liveness is the correct contract.

## Testing

Focused shell-wrapper tests will use a temporary stub Python executable and short heartbeat interval to prove:

1. `started` and heartbeat lines reach stdout before child completion.
2. Detailed child output remains in the local log.
3. The child exit code is preserved.
4. Termination reaches the child and the heartbeat loop is cleaned up promptly.
5. Existing success/failure summary behavior remains compatible.

After focused tests pass, run Bash syntax validation, the complete EOD script-test module, and one controlled OpenClaw invocation against an already-repaired date. The operational check must report `ok`, delivered output, and no residual process.

## Acceptance Criteria

- OpenClaw receives output well within the 1,200-second no-output window.
- Long-running repair details remain in the existing log rather than flooding command output.
- Success, business failure, and interruption all leave truthful terminal status.
- No heartbeat or repair child remains after wrapper exit.
- The existing schedule, timeout configuration, and Feishu destination remain unchanged.
- Focused automated tests and controlled runtime verification pass.

## Rollback

Revert the wrapper and focused test commit. No database migration or data rollback is required.
