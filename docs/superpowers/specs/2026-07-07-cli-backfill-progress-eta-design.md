# CLI Backfill Progress ETA Design

## Goal

Provide a reusable CLI progress display with elapsed time and ETA for long-running stock data backfills, starting with BaoStock minute backfill and daily close daily-bar stage.

## Scope

- Add a zero-dependency progress renderer that can be reused by CLI commands and pipeline stages.
- Preserve existing machine-readable stdout summaries.
- Prefer stderr for human progress output.
- Support TTY single-line refresh and non-TTY structured progress lines.
- Keep existing `format_progress_bar` behavior compatible.

## Design

Create `stock_research.cli_progress` with:

- `format_progress_bar(completed, total, width=24)`.
- `format_duration(seconds)` returning `HH:MM:SS`.
- `estimate_eta_seconds(completed, total, elapsed_seconds)`.
- `ProgressRenderer`, which accepts event dictionaries containing `completed`, `total`, optional `rows`, `success`, `failed`, `label`, and `event`.

The renderer writes to `stderr`. If the stream is a TTY it rewrites one line with `\r`; otherwise it emits interval-friendly lines like:

```text
progress|minute5_backfill|completed|124|total|5191|pct|2.39|elapsed|00:12:31|eta|08:30:10|rows|5952|success|123|failed|1
```

`run-baostock-minute-backfill` will pass a renderer callback into the existing `progress` argument. `run_daily_stage` will accept an optional `progress` callback and emit stage events for the main source phases.

## Non-Goals

- Do not add `tqdm`, `rich`, or other CLI UI dependencies.
- Do not change final stdout summary formats.
- Do not replace all backfill commands in this pass.

## Testing

- Unit-test progress bar, duration, ETA, TTY rendering, and non-TTY rendering.
- Test minute backfill CLI passes a progress callback and prints final summary unchanged.
- Test daily stage emits progress events when a callback is supplied.
