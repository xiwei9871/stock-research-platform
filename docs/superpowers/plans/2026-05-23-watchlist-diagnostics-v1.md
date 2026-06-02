# Watchlist Diagnostics v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a diagnostics-oriented watchlist workflow that uses `manual_v1` top-50 names as the base pool, enriches them with Dragon/LHB/technical/event diagnostics, and writes both full diagnostics and must-watch outputs.

**Architecture:** Reuse the existing watchlist workflow as the orchestration layer, but add a dedicated diagnostics module under `watchlist/` so candidate loading, diagnostics enrichment, and report shaping stay separated. Extend the current watchlist report path only where needed for the new `risk_watch` / `opportunity_watch` outputs and keep all ranking rule-based and explainable.

**Tech Stack:** Python, pandas, existing Postgres-backed store helpers, existing watchlist/report CLI, pytest.

---

## File Structure

- Create: `src/stock_research/watchlist/diagnostics.py`
  - Build the diagnostics frame from `manual_v1` top scores and optional Dragon/LHB/event inputs.
- Create: `tests/test_watchlist_diagnostics.py`
  - Unit coverage for rule logic, fallback handling, and must-watch sizing.
- Modify: `src/stock_research/watchlist/workflow.py`
  - Add orchestration entry for diagnostics generation and keep snapshot logic separate.
- Modify: `src/stock_research/reports/watchlist_report.py`
  - Support the richer diagnostics fields and `risk_watch` / `opportunity_watch` markdown sections.
- Modify: `src/stock_research/cli.py`
  - Add a dedicated `build-watchlist-diagnostics` CLI.
- Modify: `tests/test_watchlist_cli.py`
  - Cover the new CLI and output summary behavior.
- Modify: `tests/test_watchlist_report.py`
  - Cover the new markdown and CSV output behavior.

## Task 1: Add failing diagnostics tests

**Files:**
- Create: `tests/test_watchlist_diagnostics.py`
- Test: `tests/test_watchlist_diagnostics.py`

- [ ] **Step 1: Write the failing test for base candidate diagnostics build**

```python
import pandas as pd

from stock_research.watchlist.diagnostics import build_watchlist_diagnostics


def test_build_watchlist_diagnostics_builds_full_and_must_watch_outputs():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 91.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 2, "score_total": 82.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha", "amount_vs_20d": 1.4, "volatility_5d": 0.05, "high_to_close_drawdown": 0.02},
            {"asset_id": "B", "stock_name": "Beta", "amount_vs_20d": 4.8, "volatility_5d": 0.14, "high_to_close_drawdown": 0.11},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=pd.DataFrame(),
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    assert set(result) == {"full", "must_watch"}
    assert list(result["full"]["asset_id"]) == ["A", "B"]
    assert set(result["must_watch"]["watch_group"]) <= {"risk_watch", "opportunity_watch"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest -q tests/test_watchlist_diagnostics.py::test_build_watchlist_diagnostics_builds_full_and_must_watch_outputs`

Expected: FAIL with `ModuleNotFoundError` or missing symbol for `build_watchlist_diagnostics`.

- [ ] **Step 3: Write the failing test for risk/opportunity classification**

```python
def test_build_watchlist_diagnostics_assigns_risk_and_opportunity_groups():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 2, "score_total": 88.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha", "amount_vs_20d": 1.3, "volatility_5d": 0.04, "high_to_close_drawdown": 0.02},
            {"asset_id": "B", "stock_name": "Beta", "amount_vs_20d": 5.5, "volatility_5d": 0.16, "high_to_close_drawdown": 0.12},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.20, "overheat_avoid": False, "crowded_late_entry": False},
            {"asset_id": "B", "dragon_risk_score": 0.82, "overheat_avoid": True, "crowded_late_entry": True},
        ]
    )
    event_frame = pd.DataFrame(
        [
            {"asset_id": "A", "event_structure": "second_wave_candidate", "failure_flag": False},
            {"asset_id": "B", "event_structure": "a_kill_failure", "failure_flag": True},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=event_frame,
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "watch_group"] == "opportunity_watch"
    assert full.loc["B", "watch_group"] == "risk_watch"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `./.venv/bin/pytest -q tests/test_watchlist_diagnostics.py::test_build_watchlist_diagnostics_assigns_risk_and_opportunity_groups`

Expected: FAIL because diagnostics implementation does not exist yet.

- [ ] **Step 5: Commit**

```bash
git add tests/test_watchlist_diagnostics.py
git commit -m "test: add watchlist diagnostics v1 coverage"
```

## Task 2: Implement diagnostics module

**Files:**
- Create: `src/stock_research/watchlist/diagnostics.py`
- Test: `tests/test_watchlist_diagnostics.py`

- [ ] **Step 1: Write minimal implementation for diagnostics frame assembly**

```python
from __future__ import annotations

import pandas as pd


ALLOWED_OPPORTUNITY_STRUCTURES = {
    "second_wave_candidate",
    "break_then_reversal_candidate",
    "weak_to_strong_candidate",
    "trend_continuation_candidate",
}

EXCLUDED_FAILURE_STRUCTURES = {
    "a_kill_failure",
    "failed_second_wave",
    "high_open_low_close_failure",
    "one_day_pump",
}


def build_watchlist_diagnostics(
    *,
    trade_date: str,
    top_scores: pd.DataFrame,
    factor_frame: pd.DataFrame,
    dragon_frame: pd.DataFrame,
    lhb_frame: pd.DataFrame,
    event_frame: pd.DataFrame,
    market_frame: pd.DataFrame,
    risk_watch_n: int,
    opportunity_watch_n: int,
) -> dict[str, pd.DataFrame]:
    frame = top_scores.copy()
    frame = frame.rename(columns={"rank": "score_rank"})
    frame["trade_date"] = trade_date
    frame = frame.merge(factor_frame, on="asset_id", how="left")
    frame = frame.merge(dragon_frame, on="asset_id", how="left")
    frame = frame.merge(lhb_frame, on="asset_id", how="left")
    frame = frame.merge(event_frame, on="asset_id", how="left")
    frame = frame.merge(market_frame, on="asset_id", how="left")
    frame["watch_group"] = frame.apply(_classify_watch_group, axis=1)
    frame["watch_priority"] = frame.apply(_priority_value, axis=1)
    frame["diagnostic_reason"] = frame.apply(_diagnostic_reason, axis=1)
    frame["risk_note"] = frame.apply(_risk_note, axis=1)
    frame["opportunity_note"] = frame.apply(_opportunity_note, axis=1)
    frame["failure_flag"] = frame["failure_flag"].fillna(False).map(bool)
    frame["opportunity_flag"] = frame["watch_group"].eq("opportunity_watch")

    risk_rows = frame[frame["watch_group"] == "risk_watch"].sort_values(
        by=["watch_priority", "score_rank", "asset_id"]
    ).head(risk_watch_n)
    opportunity_rows = frame[frame["watch_group"] == "opportunity_watch"].sort_values(
        by=["watch_priority", "score_rank", "asset_id"]
    ).head(opportunity_watch_n)
    must_watch = pd.concat([risk_rows, opportunity_rows], ignore_index=True)
    return {"full": frame.sort_values(["score_rank", "asset_id"]).reset_index(drop=True), "must_watch": must_watch}
```

- [ ] **Step 2: Add minimal rule helpers**

```python
def _classify_watch_group(row: pd.Series) -> str:
    structure = str(row.get("event_structure") or "")
    dragon_risk = float(row.get("dragon_risk_score") or 0.0)
    lhb_risk = float(row.get("lhb_risk_score") or 0.0)
    amount_vs_20d = float(row.get("amount_vs_20d") or 0.0)
    high_to_close_drawdown = float(row.get("high_to_close_drawdown") or 0.0)

    if structure in EXCLUDED_FAILURE_STRUCTURES:
        return "risk_watch"
    if dragon_risk >= 0.7 or lhb_risk >= 0.7:
        return "risk_watch"
    if amount_vs_20d >= 4.0 or high_to_close_drawdown >= 0.08:
        return "risk_watch"
    if structure in ALLOWED_OPPORTUNITY_STRUCTURES:
        return "opportunity_watch"
    return "candidate"


def _priority_value(row: pd.Series) -> int:
    if row.get("watch_group") == "risk_watch":
        return 0
    if row.get("watch_group") == "opportunity_watch":
        return 1
    return 2


def _diagnostic_reason(row: pd.Series) -> str:
    structure = str(row.get("event_structure") or "unknown")
    return f"{row.get('watch_group')}:{structure}"


def _risk_note(row: pd.Series) -> str:
    notes = []
    if float(row.get("dragon_risk_score") or 0.0) >= 0.7:
        notes.append("dragon_risk_high")
    if float(row.get("lhb_risk_score") or 0.0) >= 0.7:
        notes.append("lhb_risk_high")
    if float(row.get("amount_vs_20d") or 0.0) >= 4.0:
        notes.append("extreme_amount")
    if float(row.get("high_to_close_drawdown") or 0.0) >= 0.08:
        notes.append("intraday_fade")
    return ",".join(notes)


def _opportunity_note(row: pd.Series) -> str:
    if row.get("watch_group") != "opportunity_watch":
        return ""
    return str(row.get("event_structure") or "")
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `./.venv/bin/pytest -q tests/test_watchlist_diagnostics.py`

Expected: PASS

- [ ] **Step 4: Refactor field defaults and fallback handling**

```python
def _ensure_columns(frame: pd.DataFrame, defaults: dict[str, object]) -> pd.DataFrame:
    result = frame.copy()
    for column, value in defaults.items():
        if column not in result.columns:
            result[column] = value
    return result
```

Apply it before classification for:
- Dragon fields
- LHB fields
- event fields
- market/mainline fields

- [ ] **Step 5: Re-run tests**

Run: `./.venv/bin/pytest -q tests/test_watchlist_diagnostics.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/watchlist/diagnostics.py tests/test_watchlist_diagnostics.py
git commit -m "feat: add watchlist diagnostics module"
```

## Task 3: Wire diagnostics into watchlist workflow

**Files:**
- Modify: `src/stock_research/watchlist/workflow.py`
- Test: `tests/test_watchlist_cli.py`

- [ ] **Step 1: Write the failing workflow test**

```python
def test_watchlist_build_cli_can_build_diagnostics(monkeypatch, capsys):
    import stock_research.cli as cli

    calls = {}

    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_diagnostics_snapshot",
        lambda **kwargs: calls.setdefault("build", kwargs) or {
            "full": pd.DataFrame([{"trade_date": "2026-05-20", "watch_group": "risk_watch"}]),
            "must_watch": pd.DataFrame([{"trade_date": "2026-05-20", "watch_group": "risk_watch"}]),
        },
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_diagnostics_report",
        lambda *args, **kwargs: {
            "markdown_path": "/tmp/watchlist.md",
            "full_csv_path": "/tmp/full.csv",
            "must_watch_csv_path": "/tmp/must_watch.csv",
        },
    )

    cli.main_for_args(
        [
            "build-watchlist-diagnostics",
            "--trade-date", "2026-05-20",
            "--score-version", "manual_v1",
        ]
    )

    assert calls["build"]["top_n"] == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest -q tests/test_watchlist_cli.py::test_watchlist_build_cli_can_build_diagnostics`

Expected: FAIL because CLI and workflow entry do not exist.

- [ ] **Step 3: Add workflow orchestration entry**

```python
def build_watchlist_diagnostics_snapshot(
    *,
    trade_date: str,
    score_version: str = "manual_v1",
    top_n: int = 50,
    risk_watch_n: int = 10,
    opportunity_watch_n: int = 10,
) -> dict[str, pd.DataFrame]:
    top_scores = _load_top_score_frame(trade_date=trade_date, score_version=score_version, top_n=top_n)
    factor_frame = _load_watchlist_factor_frame(trade_date=trade_date, asset_ids=top_scores["asset_id"].tolist())
    dragon_frame = _load_dragon_frame(trade_date=trade_date, asset_ids=top_scores["asset_id"].tolist())
    lhb_frame = _load_lhb_frame(trade_date=trade_date, asset_ids=top_scores["asset_id"].tolist())
    event_frame = _load_event_frame(trade_date=trade_date, asset_ids=top_scores["asset_id"].tolist())
    market_frame = _load_market_frame(trade_date=trade_date, asset_ids=top_scores["asset_id"].tolist())
    return build_watchlist_diagnostics(
        trade_date=trade_date,
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=event_frame,
        market_frame=market_frame,
        risk_watch_n=risk_watch_n,
        opportunity_watch_n=opportunity_watch_n,
    )
```

- [ ] **Step 4: Re-run the workflow test**

Run: `./.venv/bin/pytest -q tests/test_watchlist_cli.py::test_watchlist_build_cli_can_build_diagnostics`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/watchlist/workflow.py tests/test_watchlist_cli.py
git commit -m "feat: wire watchlist diagnostics workflow"
```

## Task 4: Add diagnostics CLI

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_watchlist_cli.py`

- [ ] **Step 1: Write the failing parser test**

```python
def test_cli_accepts_build_watchlist_diagnostics_command():
    args = build_parser().parse_args(
        [
            "build-watchlist-diagnostics",
            "--trade-date", "2026-05-20",
            "--score-version", "manual_v1",
            "--top-n", "50",
            "--risk-watch-n", "10",
            "--opportunity-watch-n", "10",
            "--output-dir", "outputs/research",
        ]
    )

    assert args.command == "build-watchlist-diagnostics"
    assert args.top_n == 50
    assert args.risk_watch_n == 10
    assert args.opportunity_watch_n == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest -q tests/test_watchlist_cli.py::test_cli_accepts_build_watchlist_diagnostics_command`

Expected: FAIL because parser entry does not exist.

- [ ] **Step 3: Add CLI parser and main dispatch**

```python
watchlist_diagnostics = subparsers.add_parser("build-watchlist-diagnostics")
watchlist_diagnostics.add_argument("--trade-date", required=True)
watchlist_diagnostics.add_argument("--score-version", default="manual_v1")
watchlist_diagnostics.add_argument("--top-n", type=int, default=50)
watchlist_diagnostics.add_argument("--risk-watch-n", type=int, default=10)
watchlist_diagnostics.add_argument("--opportunity-watch-n", type=int, default=10)
watchlist_diagnostics.add_argument("--output-dir", default="outputs/research")
```

Main dispatch:

```python
result = build_watchlist_diagnostics_snapshot(
    trade_date=args.trade_date,
    score_version=args.score_version,
    top_n=args.top_n,
    risk_watch_n=args.risk_watch_n,
    opportunity_watch_n=args.opportunity_watch_n,
)
paths = write_watchlist_diagnostics_report(
    full_rows=result["full"],
    must_watch_rows=result["must_watch"],
    output_dir=args.output_dir,
)
print(f"watchlist_diagnostics|full|{paths['full_csv_path']}")
print(f"watchlist_diagnostics|must_watch|{paths['must_watch_csv_path']}")
print(f"watchlist_diagnostics|markdown|{paths['markdown_path']}")
```

- [ ] **Step 4: Run CLI tests**

Run: `./.venv/bin/pytest -q tests/test_watchlist_cli.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/cli.py tests/test_watchlist_cli.py
git commit -m "feat: add watchlist diagnostics cli"
```

## Task 5: Extend watchlist report output

**Files:**
- Modify: `src/stock_research/reports/watchlist_report.py`
- Test: `tests/test_watchlist_report.py`

- [ ] **Step 1: Write the failing report test for must-watch groups**

```python
def test_write_watchlist_report_renders_risk_and_opportunity_sections(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "watch_group": "risk_watch",
                "watch_priority": 0,
                "event_structure": "a_kill_failure",
                "diagnostic_reason": "risk_watch:a_kill_failure",
                "risk_note": "dragon_risk_high",
                "opportunity_note": "",
            },
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "B",
                "stock_code": "000002.SZ",
                "stock_name": "Beta",
                "watch_group": "opportunity_watch",
                "watch_priority": 1,
                "event_structure": "second_wave_candidate",
                "diagnostic_reason": "opportunity_watch:second_wave_candidate",
                "risk_note": "",
                "opportunity_note": "second_wave_candidate",
            },
        ]
    )

    paths = write_watchlist_diagnostics_report(
        full_rows=frame,
        must_watch_rows=frame,
        output_dir=tmp_path,
    )

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "## Risk Watch" in markdown
    assert "## Opportunity Watch" in markdown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest -q tests/test_watchlist_report.py::test_write_watchlist_report_renders_risk_and_opportunity_sections`

Expected: FAIL because diagnostics report function does not exist.

- [ ] **Step 3: Add diagnostics report writer**

```python
def write_watchlist_diagnostics_report(
    *,
    full_rows: pd.DataFrame,
    must_watch_rows: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    trade_date = _report_value(full_rows, "trade_date")
    base = f"watchlist_diagnostics_{trade_date}"
    full_csv_path = path / f"{base}.csv"
    must_watch_csv_path = path / f"watchlist_must_watch_{trade_date}.csv"
    markdown_path = path / f"watchlist_must_watch_{trade_date}.md"
    full_rows.to_csv(full_csv_path, index=False)
    must_watch_rows.to_csv(must_watch_csv_path, index=False)
    markdown_path.write_text(_watchlist_diagnostics_markdown(must_watch_rows), encoding="utf-8")
    return {
        "full_csv_path": str(full_csv_path),
        "must_watch_csv_path": str(must_watch_csv_path),
        "markdown_path": str(markdown_path),
    }
```

- [ ] **Step 4: Add markdown renderer grouped by `watch_group`**

```python
def _watchlist_diagnostics_markdown(must_watch_rows: pd.DataFrame) -> str:
    lines = [f"# Watchlist Must Watch { _report_value(must_watch_rows, 'trade_date') }", ""]
    for title, key in (("Risk Watch", "risk_watch"), ("Opportunity Watch", "opportunity_watch")):
        lines.extend([f"## {title}", ""])
        rows = must_watch_rows[must_watch_rows["watch_group"] == key].to_dict("records")
        if not rows:
            lines.extend(["No rows.", ""])
            continue
        lines.append("| Asset | Name | Priority | Structure | Reason | Risk | Opportunity |")
        lines.append("| --- | --- | ---: | --- | --- | --- | --- |")
        for row in rows:
            lines.append(
                f"| {row.get('asset_id','')} | {row.get('stock_name','')} | {row.get('watch_priority','')} | "
                f"{row.get('event_structure','')} | {row.get('diagnostic_reason','')} | "
                f"{row.get('risk_note','')} | {row.get('opportunity_note','')} |"
            )
        lines.append("")
    return \"\\n\".join(lines).rstrip() + \"\\n\"
```

- [ ] **Step 5: Re-run report tests**

Run: `./.venv/bin/pytest -q tests/test_watchlist_report.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/reports/watchlist_report.py tests/test_watchlist_report.py
git commit -m "feat: add watchlist diagnostics reports"
```

## Task 6: Full verification

**Files:**
- Modify: none
- Test: `tests/test_watchlist_diagnostics.py`
- Test: `tests/test_watchlist_cli.py`
- Test: `tests/test_watchlist_report.py`

- [ ] **Step 1: Run targeted diagnostics suite**

Run: `./.venv/bin/pytest -q tests/test_watchlist_diagnostics.py tests/test_watchlist_cli.py tests/test_watchlist_report.py`

Expected: PASS

- [ ] **Step 2: Run broader workflow regression**

Run: `./.venv/bin/pytest -q tests/test_factor_store.py tests/test_daily_pipeline.py tests/test_daily_incremental.py`

Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `./.venv/bin/pytest -q`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/watchlist/diagnostics.py \
        src/stock_research/watchlist/workflow.py \
        src/stock_research/reports/watchlist_report.py \
        src/stock_research/cli.py \
        tests/test_watchlist_diagnostics.py \
        tests/test_watchlist_cli.py \
        tests/test_watchlist_report.py
git commit -m "feat: add watchlist diagnostics v1"
```

## Self-Review

- Spec coverage:
  - base pool from `manual_v1 top_n=50`: covered by Tasks 2-4;
  - `risk_watch` / `opportunity_watch`: covered by Task 2;
  - full + must-watch outputs: covered by Tasks 2 and 5;
  - graceful degradation on missing optional inputs: covered by Task 2 fallback handling;
  - CLI and report outputs: covered by Tasks 4 and 5.
- Placeholder scan:
  - no `TODO` / `TBD` placeholders;
  - every code-changing step includes explicit code and test command.
- Type consistency:
  - `build_watchlist_diagnostics()`, `build_watchlist_diagnostics_snapshot()`, and `write_watchlist_diagnostics_report()` use the same names throughout the plan.
