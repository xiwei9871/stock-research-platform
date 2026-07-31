# Codex Retained Reasoning And Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make retained reasoning and automatic context compaction work globally in Codex by preserving the Responses conversation path and removing stale context-window overrides.

**Architecture:** Keep the existing global OpenAI-compatible provider, Responses wire protocol, response storage, model selection, and all unrelated Codex settings unchanged. Back up the user configuration, remove only the two manual context limits, then validate strict parsing, feature availability, and a persisted two-turn Responses conversation through the installed Codex CLI.

**Tech Stack:** Codex CLI 0.146.x, TOML user configuration, Responses API, zsh, `rtk`, `jq`

---

## File Structure

- Modify: `/Users/xiwei/.codex/config.toml` — global Codex settings used across repositories.
- Create: `/Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction` — exact pre-change rollback copy.
- Inspect only: `/Users/xiwei/.codex/sessions/<year>/<month>/<day>/rollout-*.jsonl` — persisted smoke-test session evidence.
- Do not modify: `/Users/xiwei/stock_research` application code, tests, dashboard, runtime configuration, output CSV files, or `.learnings/` content.

### Task 1: Capture The Global Configuration Baseline

**Files:**
- Inspect: `/Users/xiwei/.codex/config.toml`
- Create: `/Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction`

- [ ] **Step 1: Confirm the target settings have the expected pre-change values**

Run:

```bash
rtk rg -n '^(model_provider|model|disable_response_storage|model_context_window|model_auto_compact_token_limit) =|^\[model_providers\.OpenAI\]|^wire_api =' /Users/xiwei/.codex/config.toml
```

Expected output includes exactly these relevant values:

```text
model_provider = "OpenAI"
model = "gpt-5.6-sol"
disable_response_storage = false
model_context_window = 500000
model_auto_compact_token_limit = 900000
[model_providers.OpenAI]
wire_api = "responses"
```

- [ ] **Step 2: Confirm the deterministic backup path is unused**

Run:

```bash
rtk test ! -e /Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction
```

Expected: exit code 0 with no output. If the path already exists, stop and compare it with the current configuration; do not overwrite it.

- [ ] **Step 3: Create a metadata-preserving rollback copy**

Run:

```bash
rtk cp -p /Users/xiwei/.codex/config.toml /Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction
```

Expected: exit code 0.

- [ ] **Step 4: Verify the backup is byte-identical**

Run:

```bash
rtk cmp /Users/xiwei/.codex/config.toml /Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction
```

Expected: exit code 0 with no differences.

### Task 2: Remove Only The Stale Context Overrides

**Files:**
- Modify: `/Users/xiwei/.codex/config.toml:8-9`

- [ ] **Step 1: Apply the minimal configuration edit**

Use `apply_patch` with this exact patch:

```diff
*** Begin Patch
*** Update File: /Users/xiwei/.codex/config.toml
@@
-model_context_window = 500000
-model_auto_compact_token_limit = 900000
 approvals_reviewer = "user"
*** End Patch
```

Expected: only the two obsolete settings are removed.

- [ ] **Step 2: Compare the edited configuration with its backup**

Run:

```bash
rtk diff -u /Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction /Users/xiwei/.codex/config.toml
```

Expected diff:

```diff
-model_context_window = 500000
-model_auto_compact_token_limit = 900000
```

No provider URL, authentication, model, reasoning effort, sandbox, MCP, plugin, desktop, or notification line may change.

- [ ] **Step 3: Confirm retained-reasoning prerequisites remain present**

Run:

```bash
rtk rg -n '^(model_provider|model|disable_response_storage) =|^\[model_providers\.OpenAI\]|^wire_api =' /Users/xiwei/.codex/config.toml
```

Expected output includes:

```text
model_provider = "OpenAI"
model = "gpt-5.6-sol"
disable_response_storage = false
[model_providers.OpenAI]
wire_api = "responses"
```

### Task 3: Validate Configuration And Compaction Availability

**Files:**
- Inspect: `/Users/xiwei/.codex/config.toml`

- [ ] **Step 1: Parse the full configuration in strict mode**

Run:

```bash
rtk codex --strict-config --version
```

Expected: exit code 0 and a `codex-cli 0.146.x` version line. Any unknown-field or TOML parse error fails this task.

- [ ] **Step 2: Confirm no manual context sizing remains**

Run:

```bash
rtk rg -n '^model_context_window =|^model_auto_compact_token_limit =|^model_auto_compact_token_limit_scope =' /Users/xiwei/.codex/config.toml
```

Expected: exit code 1 with no matching lines. This is the expected `rg` no-match result.

- [ ] **Step 3: Confirm the installed runtime has compaction enabled**

Run:

```bash
rtk codex features list | rtk rg '^remote_compaction_v2\s+stable\s+true$'
```

Expected:

```text
remote_compaction_v2                 stable             true
```

- [ ] **Step 4: Confirm the provider remains on the only supported wire protocol**

Run:

```bash
rtk rg -n -A4 '^\[model_providers\.OpenAI\]$' /Users/xiwei/.codex/config.toml
```

Expected: the provider block still contains `wire_api = "responses"` and its original base URL and authentication setting.

### Task 4: Verify A Persisted Two-Turn Responses Conversation

**Files:**
- Create temporarily: a directory returned by `mktemp -d`
- Create automatically: one persisted Codex session under `/Users/xiwei/.codex/sessions/`

- [ ] **Step 1: Create an isolated verification directory**

Run:

```bash
CODEX_RETENTION_VERIFY_DIR=$(rtk mktemp -d)
rtk test -n "$CODEX_RETENTION_VERIFY_DIR"
```

Expected: exit code 0 and a new empty temporary directory. Keep this shell session active for the remaining task steps.

- [ ] **Step 2: Start a persisted first turn using the global configuration**

Run:

```bash
rtk proxy codex exec --strict-config --skip-git-repo-check --sandbox read-only --json -C "$CODEX_RETENTION_VERIFY_DIR" 'Remember the marker RETAINED-7319 for the next turn. Reply with exactly FIRST_OK.' | rtk proxy tee "$CODEX_RETENTION_VERIFY_DIR/turn-1.jsonl"
```

Expected:

- exit code 0;
- a `thread.started` event containing a thread/session ID;
- a completed assistant response containing `FIRST_OK`;
- no `previous response was not found`, unsupported `wire_api`, or configuration error.

- [ ] **Step 3: Extract and validate the persisted thread ID**

Run:

```bash
CODEX_RETENTION_THREAD_ID=$(rtk proxy jq -r 'select(.type == "thread.started") | .thread_id' "$CODEX_RETENTION_VERIFY_DIR/turn-1.jsonl" | rtk proxy head -1)
rtk test -n "$CODEX_RETENTION_THREAD_ID"
```

Expected: exit code 0 and a non-empty UUID in `CODEX_RETENTION_THREAD_ID`.

- [ ] **Step 4: Resume the exact thread and test retained conversational state**

Run:

```bash
rtk proxy codex exec resume --strict-config --skip-git-repo-check --json "$CODEX_RETENTION_THREAD_ID" 'Reply with only the marker you were asked to remember.' | rtk proxy tee "$CODEX_RETENTION_VERIFY_DIR/turn-2.jsonl"
```

Expected:

- exit code 0;
- final assistant output contains exactly `RETAINED-7319`;
- no missing-previous-response, unsupported Responses protocol, or provider error.

- [ ] **Step 5: Locate the persisted rollout and inspect response-state evidence**

Run:

```bash
CODEX_RETENTION_ROLLOUT=$(rtk rg -l "$CODEX_RETENTION_THREAD_ID" /Users/xiwei/.codex/sessions --glob 'rollout-*.jsonl' | rtk proxy head -1)
rtk test -n "$CODEX_RETENTION_ROLLOUT"
rtk proxy jq -c 'select(.type == "response_item" and (.payload.type == "reasoning" or .payload.type == "message")) | {type:.payload.type,id:.payload.id,has_encrypted_reasoning:(.payload.encrypted_content != null)}' "$CODEX_RETENTION_ROLLOUT" | rtk proxy head -20
```

Expected: persisted response items have non-empty IDs; reasoning items, when emitted by the model, report encrypted reasoning content. Absence of a reasoning item in this tiny smoke test is not a failure if the two-turn marker test passes.

- [ ] **Step 6: Remove only the temporary verification directory**

Run:

```bash
rtk test -n "$CODEX_RETENTION_VERIFY_DIR"
rtk test "$CODEX_RETENTION_VERIFY_DIR" != "/"
rtk rm -rf "$CODEX_RETENTION_VERIFY_DIR"
```

Expected: the temporary command-output directory is removed. Keep the persisted Codex rollout as verification evidence.

### Task 5: Verify Scope And Record The Handoff

**Files:**
- Inspect: `/Users/xiwei/stock_research`
- Inspect: `/Users/xiwei/.codex/config.toml`

- [ ] **Step 1: Confirm the repository has no implementation changes from this task**

Run:

```bash
rtk git status --short
```

Expected: only the user's pre-existing modified output CSV files and untracked `.learnings/` entry are present. No application, test, dashboard, script, project configuration, or documentation file should be newly modified by implementation.

- [ ] **Step 2: Report the final configuration delta and rollback path**

Report all of the following:

```text
Removed global overrides:
- model_context_window = 500000
- model_auto_compact_token_limit = 900000

Preserved:
- model_provider = "OpenAI"
- model = "gpt-5.6-sol"
- disable_response_storage = false
- model_providers.OpenAI.wire_api = "responses"

Rollback copy:
/Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction
```

- [ ] **Step 3: State the immediate verification results precisely**

Report:

- strict configuration parsing result and installed Codex version;
- `remote_compaction_v2` feature status;
- first-turn and resumed-turn outputs;
- whether response item IDs and encrypted reasoning evidence were present;
- that compaction itself was not artificially forced, because doing so would waste tokens and could distort normal long-task behavior.

### Task 6: Roll Back Only If A Required Verification Fails

**Files:**
- Restore if required: `/Users/xiwei/.codex/config.toml`
- Source: `/Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction`

- [ ] **Step 1: Restore the backup after a strict-parse or provider-regression failure**

Run this only when Task 3 or the provider startup portion of Task 4 fails:

```bash
rtk cp -p /Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction /Users/xiwei/.codex/config.toml
```

Expected: exit code 0.

- [ ] **Step 2: Verify the restored file is byte-identical to the backup**

Run:

```bash
rtk cmp /Users/xiwei/.codex/config.toml /Users/xiwei/.codex/config.toml.bak.20260731-retained-reasoning-compaction
rtk codex --strict-config --version
```

Expected: both commands exit 0. Report the original failing command and its exact error; do not attempt provider, credential, model, or endpoint changes without a new design decision.
