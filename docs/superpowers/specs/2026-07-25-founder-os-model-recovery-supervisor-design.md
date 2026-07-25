# Founder OS Model Recovery Supervisor Design

## Context

Founder OS cron jobs use `volcengine-plan/doubao-seed-2.0-code` as the primary model and `openai/gpt-5.4` as the fallback. On 2026-07-25, the primary model exhausted its weekly quota and the fallback was temporarily unavailable or rate-limited. Several independent cron jobs then emitted nearly identical failure alerts into the same Feishu group.

The desired behavior is to keep the existing two-model order, wait when both models are unavailable, and rerun every failed task from the current Shanghai calendar day as soon as either model becomes available. Tasks from a previous calendar day must not be replayed.

## Goals

- Keep the model route `Doubao -> OpenAI`.
- Do not introduce a third model.
- Automatically recover same-day tasks that failed because both configured models were unavailable.
- Rerun every eligible same-day task even if its original business time has passed.
- Prevent duplicate replays.
- Replace per-task raw provider errors with one incident-level Feishu alert and one recovery summary.
- Make the health guard independent of all language models.

## Non-goals

- Retrying business logic failures, invalid inputs, permission failures, or tool errors automatically.
- Replaying tasks from an earlier Shanghai calendar day.
- Changing task prompts, schedules, outputs, or ownership.
- Changing stock platform command jobs or their alerts.
- Adding another model provider.

## Architecture

Add a deterministic recovery supervisor invoked by an OpenClaw `command` cron every 20 minutes. The supervisor must not call a language model to inspect state, decide what to retry, or send notifications.

The supervisor reads OpenClaw cron state and recent run history, classifies failures, maintains an incident state file, triggers eligible reruns through the OpenClaw CLI, and sends short Feishu messages through the deterministic message CLI.

The implementation should live at:

- supervisor: `/Users/xiwei/.openclaw/bin/founder_os_model_recovery.py`
- state directory: `/Users/xiwei/.openclaw/state/founder-os-model-recovery/`
- state file: one JSON file per Shanghai date, named `YYYY-MM-DD.json`
- operational log: `/Users/xiwei/.openclaw/logs/founder-os-model-recovery.log`

## Managed Task Scope

The supervisor manages enabled OpenClaw cron jobs whose payload kind is `agentTurn`. It excludes:

- itself;
- command-based stock and platform jobs;
- orchestration dashboard synchronization;
- disabled jobs;
- tasks whose latest failure belongs to a previous Shanghai calendar day.

This rule allows the supervisor to recover Founder OS, Watson, Athena, Friday, Jarvis, and Obsidian model-driven tasks without maintaining a fragile hard-coded task list.

## Failure Classification

A failed run is eligible for automatic replay only when its normalized error contains a configured model-availability signature:

- HTTP `429` quota or rate-limit errors;
- `usage limit` or `weekly usage quota`;
- `auth_unavailable`;
- `no auth available`;
- `credentials ... cooling down`;
- `All models failed` when every nested cause is a model-availability failure.

If `All models failed` contains any business, tool, prompt, permission, or filesystem failure, the run is not eligible for automatic replay.

Non-model failures are recorded and included in one aggregate alert, but they are not rerun automatically.

## Recovery Flow

On each 20-minute supervisor cycle:

1. Resolve the current date in `Asia/Shanghai`.
2. Read enabled cron jobs and their latest run state.
3. Select failures whose latest failed run occurred on the current Shanghai date.
4. Remove tasks already marked recovered, terminal, or intentionally skipped in today's state file.
5. Classify each remaining failure as model-unavailable or non-model.
6. For model-unavailable tasks, enforce a 20-minute probe cooldown.
7. Retry one oldest pending task as the recovery probe.
8. Poll the resulting run to a terminal state.
9. If the probe fails again with a model-availability error, record the attempt and stop the cycle without retrying the other tasks.
10. If the probe succeeds, rerun all other pending same-day model-unavailable tasks sequentially and record each outcome.
11. Never rerun a task more than once after it has succeeded for the original failed run.
12. At the Shanghai date boundary, start a new state file and never import unresolved tasks from yesterday.

Sequential replay avoids consuming both model routes with a burst of simultaneous retries immediately after recovery.

## Incident and Deduplication State

Each state file records:

- incident identifier and first detection time;
- original failed run ID and timestamp per job;
- normalized failure classification;
- probe attempts and timestamps;
- replay run IDs and terminal outcomes;
- whether the outage alert was sent;
- whether the recovery or end-of-day unresolved summary was sent.

The deduplication key is the pair `(job_id, original_failed_run_id)`. A later independent failure from the same job is a new item.

State updates must use atomic replace semantics so interruption cannot leave a partially written JSON file.

## Notification Policy

Managed `agentTurn` jobs no longer send their individual raw failure alerts to the Founder OS Feishu group. The supervisor owns notifications for this scope.

It sends at most:

1. One outage message when the first incident is detected, containing the affected task count, the unavailable model routes, and the next retry time.
2. One recovery message after all eligible same-day tasks have either succeeded or ended with a non-model failure.
3. One unresolved summary near 23:50 if model-unavailable tasks remain pending.

Messages must not include request IDs, stack traces, raw provider payloads, or repeated heartbeat output. Non-model failures are summarized by task name and concise classification.

## Health Guard

Replace `founder-os-cron-health-guard`'s `agentTurn` payload with a deterministic command invoking the supervisor in audit mode. Audit mode checks state consistency, stale pending replays, and supervisor execution freshness without calling a model.

The recurring 20-minute supervisor job performs recovery. The existing health-guard schedule provides a separate deterministic daily audit.

## Configuration Changes

- Preserve every managed agent's primary model and fallback order.
- Do not add a third fallback.
- Disable per-job model failure alerts for managed `agentTurn` jobs after exporting their existing cron definitions for rollback.
- Keep delivery behavior for successful task outputs unchanged.
- Add the deterministic 20-minute recovery supervisor cron.
- Convert the existing health guard to a deterministic command payload.

## Error Handling

- Failure to read cron state: log locally and send no repeated group alert; retry next cycle.
- Failure to persist state: do not trigger replay, preventing duplicate execution.
- Replay command timeout: poll run history once more, then mark the replay outcome unknown and do not start another replay for that item in the same cycle.
- Feishu notification failure: retain an unsent notification flag and retry delivery next cycle without rerunning tasks.
- Supervisor overlap: use a non-blocking local lock; a second instance exits successfully and records a short log entry.

## Testing

Unit tests must cover:

- Shanghai-day filtering at UTC date boundaries;
- model-availability and non-model error classification;
- mixed `All models failed` causes;
- incident deduplication;
- probe cooldown;
- successful probe followed by sequential replay;
- failed probe stopping the cycle;
- no replay across date boundaries;
- atomic state transitions;
- notification deduplication and redaction.

CLI-level tests use fixture cron JSON and fake run/message commands. They must not invoke a real model or send a real Feishu message.

Before rollout:

- export all affected cron definitions;
- run the supervisor in dry-run mode against current cron state;
- verify that today's historical failures are identified but not replayed if outside the current test window;
- verify the health guard command and lock behavior;
- perform one controlled recovery test with a disposable cron fixture.

## Acceptance Criteria

- Doubao remains primary and OpenAI remains the only fallback.
- When both routes fail, only one aggregate incident alert is delivered.
- The supervisor waits without repeatedly invoking every failed task.
- When either route recovers on the same Shanghai date, every eligible failed task is replayed exactly once until success or a non-model failure.
- No previous-day task is replayed.
- The health guard runs successfully when both language-model routes are unavailable.
- Successful task delivery remains unchanged.
- Rollback restores the exported cron definitions and removes the supervisor cron without losing incident evidence.

## Rollback

Rollback consists of disabling the supervisor cron, restoring the exported cron definitions, restoring the original health-guard payload, and retaining state/log files as audit evidence. No task outputs are deleted.
