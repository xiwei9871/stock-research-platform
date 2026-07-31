# Codex Retained Reasoning And Compaction Global Configuration Design

## Goal

Configure the local Codex installation so all projects benefit from retained
reasoning and automatic context compaction without pinning stale model context
limits.

## Current State

The user-level Codex configuration is stored at
`/Users/xiwei/.codex/config.toml` and currently contains:

```toml
model_provider = "OpenAI"
model = "gpt-5.6-sol"
disable_response_storage = false
network_access = "enabled"
windows_wsl_setup_acknowledged = true
model_context_window = 500000
model_auto_compact_token_limit = 900000

[model_providers.OpenAI]
wire_api = "responses"
```

The active GPT-5.6 Sol session reports an effective context window of 258,400
tokens. The configured automatic-compaction threshold of 900,000 tokens is
therefore above the active context window and cannot provide a useful trigger.

Codex CLI 0.146.0 rejects `disable_response_storage` during a real
`codex exec --strict-config` startup because the field is no longer part of the
supported configuration schema. Non-strict startup ignores the stale field, so
removing it makes the configuration truthful without disabling a working
runtime capability.

Strict configuration probing also rejects the legacy top-level
`network_access` field and, on the installed macOS build, the Windows-only
`windows_wsl_setup_acknowledged` acknowledgement field. A temporary
`CODEX_HOME` probe confirmed that strict parsing advances to provider startup
after all three legacy fields are absent.

Codex already uses the Responses protocol. Its runtime supports response item
IDs, encrypted reasoning items, `previous_response_id`, and automatic history
compaction. Retained reasoning is consequently a runtime behavior of the
Responses conversation path, not a separate Codex boolean setting.

## Chosen Approach

Use Codex and model-catalog defaults for context-window sizing and automatic
compaction thresholds.

Remove these user overrides:

```toml
disable_response_storage = false
network_access = "enabled"
windows_wsl_setup_acknowledged = true
model_context_window = 500000
model_auto_compact_token_limit = 900000
```

Keep the existing Responses provider configuration:

```toml
model_provider = "OpenAI"

[model_providers.OpenAI]
wire_api = "responses"
```

Do not add `features.remote_compaction_v2`. The installed Codex runtime already
reports that stable feature as enabled, while the public configuration
reference does not require users to opt into it.

Do not set `model_auto_compact_token_limit_scope`. Without a custom threshold,
the model/runtime defaults should control both the threshold and its accounting
behavior as a compatible pair.

## Why This Approach

The public Codex configuration reference defines
`model_auto_compact_token_limit` as an optional threshold and states that an
unset value uses model defaults. Removing both manual limits prevents a future
model catalog update from being constrained by an outdated local assumption.

The same reference does not define `disable_response_storage`, and the
installed CLI rejects it in strict execution mode. Retained reasoning remains
available through Codex's Responses conversation path, response item IDs, and
encrypted reasoning state; it is not controlled by this obsolete TOML field.

The public reference scopes network access under sandbox or permission
configuration rather than the removed top-level string. The Windows onboarding
acknowledgement has no runtime purpose on this macOS installation and is
rejected by strict execution. Removing both fields is behavior-preserving in
the active environment.

An explicit fixed threshold, such as 200,000 tokens, would repair the current
misconfiguration but would need maintenance whenever the selected model or its
effective context window changes. An aggressive lower threshold would compact
more often and could discard useful detail unnecessarily.

## Runtime Flow

1. Codex selects `gpt-5.6-sol` through the configured `OpenAI` provider.
2. The provider sends requests through the Responses protocol.
3. Codex reuses server response state where available, including response item
   IDs and retained encrypted reasoning state.
4. If server-side incremental continuation is unavailable, Codex may replay the
   materialized thread history instead of losing the conversation.
5. As active context grows, Codex uses the model/runtime-derived compaction
   threshold and replaces older history with a compacted representation.
6. The compacted thread continues with current goals, decisions, tool results,
   and relevant prior context retained in summarized form.

## Provider Compatibility Boundary

The configured provider uses the custom base URL already present in the global
configuration. The change does not replace or reconfigure that provider.

For the full optimized path, the provider must correctly proxy Responses API
conversation continuation and compaction behavior. If it cannot honor a stored
previous response or a remote compaction request, Codex may retry with fuller
history or use its available fallback path. Verification must therefore check
runtime behavior, not only TOML parsing.

No API credentials, model identifiers, provider URLs, authentication settings,
reasoning effort, sandbox settings, plugins, or project configuration will be
changed.

## Implementation Safety

Before editing, preserve the timestamped sibling backup of
`/Users/xiwei/.codex/config.toml`. Apply a minimal edit that removes only the two
obsolete context overrides and the three obsolete environment/runtime fields.
Preserve all unrelated global settings and existing user customizations.

The repository currently contains unrelated modified output CSV files and an
untracked `.learnings/` entry. They are outside this task and must remain
untouched.

## Verification

After the configuration edit:

1. Start a small persisted `codex exec --strict-config` task to ensure the full
   runtime accepts the resulting TOML; version-only commands are insufficient
   because they may exit before loading execution configuration.
2. Re-read the effective configuration area and confirm both manual limits,
   `disable_response_storage`, top-level `network_access`, and
   `windows_wsl_setup_acknowledged` are absent while
   `wire_api = "responses"` remains.
3. Start a fresh Codex task so startup-time configuration is reloaded.
4. Confirm the new task reports a model-derived context window rather than the
   removed 500,000-token override.
5. Confirm subsequent turns produce response item IDs/reasoning items and do
   not report a missing or unsupported Responses continuation path.
6. For a naturally long-running task, inspect session events for successful
   compaction when the runtime-selected threshold is eventually reached. Do not
   generate large artificial token usage solely to force this verification.

## Failure Handling And Rollback

If strict execution startup fails, restore the timestamped backup and report
the exact configuration error.

If new tasks fail to use the custom provider, restore the backup and investigate
provider compatibility before attempting a broader configuration change.

If retained continuation works but remote compaction fails, keep the Responses
configuration and diagnose whether the custom provider supports the relevant
compaction endpoint. Do not silently switch the provider or change credentials.

## Sources

- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference#configtoml)
- [Responses API create reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
