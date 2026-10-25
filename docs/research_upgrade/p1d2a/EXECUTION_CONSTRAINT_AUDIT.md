# P1d.2a — Execution Constraint Audit (`_effective_execution_constraints`)

## Defect

Old code rebuilt `BacktestExecutionConstraints` field-by-field when
`transaction_cost_bps != 0`. Any field not explicitly copied — including
`block_missing_limit_state` added in P1d.2 — silently reverted to default.
A strict-mode run with nonzero cost therefore lost its missing-state block.

## Fix

```python
return dataclasses.replace(constraints,
                           commission_bps=float(config.transaction_cost_bps))
```

Structural guarantee: every present and future field is preserved; only
`commission_bps` is overridden.

## Test matrix (test_effective_constraints_preserve_missing_state_block)

| cost_bps | block_missing_limit_state | bar state | can_open_long |
|---|---|---|---|
| 0 | True | missing | `(False, "limit_state_missing")` |
| 0 | True | present | allowed |
| 15 | True | missing | `(False, "limit_state_missing")` |
| 15 | True | present | allowed |
| 0/15 | False (legacy default) | missing | allowed — reproduces old behavior |

`commission_bps` correctly materializes to 15.0 under the cost path.

## Regression check

All 4 prior shadow legs re-ran **byte-identical** (equity, drawdown,
diff keys, diff CSVs) — the replace() refactor changes nothing when the
constraint set is default.
