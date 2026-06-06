# Mid-Trend Runner Research Infra Integration Design

## Goal

Connect the standardized `research_infra` evidence artifacts to the real
mid-trend portfolio review runner through an explicit opt-in switch, while
preserving the existing review behavior by default.

This is the next stage after the method-layer adapter and wrapper:

- `write_mid_trend_research_infra_artifacts(...)`
- `build_mid_trend_review_with_research_infra(...)`

The work remains method migration, not ML4Trading code migration.

## Current Context

The isolated `method-infra-first-slice` branch already contains the committed
research infrastructure contracts and the mid-trend wrapper. The real
`mid_trend_portfolio_review.py` module currently exists in the main worktree as
uncommitted work, with this shape:

- `build_mid_trend_portfolio_review_from_frames(...)`
- `run_mid_trend_portfolio_review(...)`
- CLI command: `build-mid-trend-portfolio-review`

Because the real mid-trend module is not committed on this branch, this design
must be implemented only after that module is available in the implementation
workspace, or by applying the same design to the main worktree without
overwriting unrelated dirty changes.

## Scope

Included:

- Add `write_research_infra: bool = False` to
  `run_mid_trend_portfolio_review(...)`.
- Keep `build_mid_trend_portfolio_review_from_frames(...)` unchanged.
- In the runner, wrap the existing build call with
  `build_mid_trend_review_with_research_infra(...)`.
- Add CLI flag `--write-research-infra` to
  `build-mid-trend-portfolio-review`.
- When enabled, print stable artifact lines for downstream scripts.
- Add tests proving default behavior is unchanged and enabled behavior writes
  `research_infra`.

Excluded:

- Any automatic trading, broker, order, account, cash, or position behavior.
- Any change to review labels, ranking, markdown layout, or portfolio decision
  logic.
- Dashboard display.
- Database migrations.
- Importing ML4Trading code.
- Making sidecar generation default-on.

## Proposed Runner API

Update:

```python
def run_mid_trend_portfolio_review(
    *,
    trade_date: str,
    strategy_variant: str,
    top10_path: str | Path,
    holdings_path: str | Path,
    trades_path: str | Path,
    research_packet_path: str | Path,
    output_dir: str | Path | None = None,
    write_research_infra: bool = False,
) -> dict[str, Any]:
    ...
```

Default behavior:

- Reads the same CSV inputs.
- Writes the same review CSV and Markdown through the existing builder.
- Returns the same result shape.
- Does not create `<output_dir>/research_infra/`.

Enabled behavior:

- Calls the same builder exactly once.
- Writes standardized sidecars under `<output_dir>/research_infra/`.
- Returns all original review fields plus:

```python
{
    "research_infra": {
        "research_infra_dir": "...",
        "research_signals_json_path": "...",
        "attribution_cards_json_path": "...",
        "attribution_cards_md_path": "...",
        "experiment_registry_path": "...",
        "run_card": {...},
        "research_signal_count": 0,
        "attribution_card_count": 0,
    }
}
```

## Data Flow

1. Runner normalizes `output_dir`.
2. Runner reads `top10`, `holdings`, `trades`, and `research_packet_candidates`.
3. Runner creates a `review_builder` closure that calls
   `build_mid_trend_portfolio_review_from_frames(...)` with the existing
   arguments.
4. Runner passes that closure to
   `build_mid_trend_review_with_research_infra(...)`.
5. If `write_research_infra=False`, the wrapper returns the original review
   result unchanged.
6. If `write_research_infra=True`, the wrapper writes sidecars and returns a
   shallow copy with `research_infra`.

This keeps file-writing side effects at the runner layer and preserves the
builder as the deterministic review constructor.

## CLI Behavior

Extend:

```bash
stock-research build-mid-trend-portfolio-review \
  --trade-date 2026-06-04 \
  --strategy-variant top5_weekly_max_2_replacements \
  --top10-path ... \
  --holdings-path ... \
  --trades-path ... \
  --research-packet-path ... \
  --output-dir outputs/research \
  --write-research-infra
```

Default CLI output remains:

```text
mid_trend_portfolio_review|csv|<path>
mid_trend_portfolio_review|report|<path>
mid_trend_portfolio_review|rows|<count>
```

When enabled, append:

```text
mid_trend_portfolio_review|research_infra|<research_infra_dir>
mid_trend_portfolio_review|research_signals|<research_signals_json_path>
mid_trend_portfolio_review|attribution_cards|<attribution_cards_json_path>
mid_trend_portfolio_review|run_card|<run_card_json_path>
```

These lines are intentionally path-oriented so runbooks, cron wrappers, and
future dashboard imports can consume them without parsing Markdown.

## Error Handling

- If the review builder fails, the error propagates unchanged.
- If sidecar generation fails while `write_research_infra=True`, the command
  fails. This avoids silently producing a review without evidence when the user
  explicitly requested evidence.
- If `write_research_infra=False`, no research-infra validation or sidecar
  directory creation occurs.
- The runner should not catch and downgrade errors from
  `build_mid_trend_review_with_research_infra(...)`.

## Testing

Focused tests:

- Runner default mode still reads CSVs, delegates to the builder, returns the
  original result, and passes `write_research_infra=False`.
- Runner enabled mode returns a result containing `research_infra` and writes
  sidecars under the normalized output directory.
- CLI parser accepts `--write-research-infra`.
- CLI command passes `write_research_infra=True` to the runner.
- CLI prints the research-infra artifact paths only when the returned result
  contains `research_infra`.

Verification should include:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_mid_trend_portfolio_review.py \
  tests/test_research_infra_mid_trend_integration.py \
  -q
```

If the implementation touches shared CLI parser behavior, also run the focused
CLI parser test file that contains `build-mid-trend-portfolio-review`.

## Success Criteria

- Existing mid-trend review tests pass.
- Existing research-infra integration tests pass.
- Default runner and CLI behavior are unchanged.
- Enabled runner mode writes `research_infra` sidecars using the existing
  method-layer contracts.
- CLI exposes the sidecar locations in stable machine-readable lines.
- No trading or execution behavior is added.
