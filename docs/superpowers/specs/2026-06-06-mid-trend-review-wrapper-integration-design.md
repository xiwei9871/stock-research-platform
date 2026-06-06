# Mid-Trend Review Wrapper Integration Design

## Goal

Add a function-level integration wrapper that lets callers run an existing
mid-trend review builder and, when explicitly requested, write the standardized
`research_infra` sidecar artifacts from the returned review result.

The wrapper is the next step after `write_mid_trend_research_infra_artifacts()`.
It connects method-layer artifacts to a callable workflow without changing the
default behavior of any mid-trend review logic.

## Current Context

The `method-infra-first-slice` worktree contains:

- `src/stock_research/research_infra/mid_trend_integration.py`
- tests for sidecar generation from a toy `review_result`
- no committed `mid_trend_portfolio_review.py` module

The main worktree has many uncommitted mid-trend modules. This wrapper must not
import those uncommitted modules. Instead, it should accept a caller-provided
review builder callable. Later, once the main mid-trend modules are stable, the
same wrapper can be used with the real builder.

## Scope

Included:

- A wrapper function in `research_infra.mid_trend_integration`.
- Explicit opt-in flag for sidecar writing.
- Preservation of the original review result.
- Optional `research_infra` key added to the returned result only when sidecar
  writing is enabled.
- Tests proving default behavior does not write sidecars.
- Tests proving enabled behavior calls the review builder, writes sidecars, and
  returns both original review fields and `research_infra` metadata.

Excluded:

- Importing or modifying `mid_trend_portfolio_review.py`.
- CLI flags.
- Dashboard changes.
- Database migrations.
- Broker, order, execution, cash, account, position, or automatic promotion
  behavior.

## Proposed API

Add:

```python
def build_mid_trend_review_with_research_infra(
    *,
    trade_date: str,
    strategy_variant: str,
    review_builder: Callable[[], dict[str, Any]],
    output_dir: str | Path,
    write_research_infra: bool = False,
) -> dict[str, Any]:
    ...
```

Behavior:

- Always calls `review_builder()` exactly once.
- If `write_research_infra=False`, returns the review result unchanged and does
  not create `<output_dir>/research_infra/`.
- If `write_research_infra=True`, calls
  `write_mid_trend_research_infra_artifacts(...)` with the review result and
  returns a shallow copy of the review result plus:

```python
{
    "research_infra": <artifact result dict>
}
```

This API keeps the wrapper testable without depending on uncommitted modules.

## Data Flow

1. Caller constructs a builder closure around the existing review call.
2. Wrapper calls the builder and gets `review_result`.
3. If sidecars are disabled, wrapper returns the original result object.
4. If sidecars are enabled, wrapper writes research-infra artifacts under
   `<output_dir>/research_infra/`.
5. Wrapper returns a new result dictionary containing all original keys plus
   `research_infra`.

## Error Handling

- Builder exceptions are not swallowed. They should propagate unchanged.
- Sidecar-writing validation errors are not swallowed. They should propagate so
  the caller sees failed evidence generation.
- Non-dict review builder output raises a clear `TypeError`.

## Testing

Focused tests:

- Disabled mode returns the exact review result and does not create sidecar
  directory.
- Enabled mode writes sidecars and returns a result with `research_infra`.
- Builder is called exactly once.
- Non-dict builder result raises `TypeError`.

Verification command:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_research_infra_mid_trend_integration.py \
  tests/test_research_infra_run_evidence.py \
  tests/test_research_infra_experiment_registry.py \
  tests/test_research_infra_research_signals.py \
  tests/test_research_infra_attribution_cards.py \
  -q
```

## Success Criteria

- Existing sidecar artifact tests still pass.
- Wrapper disabled mode has zero artifact side effects.
- Wrapper enabled mode produces the same sidecars as the adapter.
- The implementation remains review-only.
- The implementation does not import uncommitted mid-trend modules.
