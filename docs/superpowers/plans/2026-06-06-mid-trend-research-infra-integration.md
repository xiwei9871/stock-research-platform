# Mid-Trend Research Infra Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a thin adapter that converts an existing mid-trend portfolio review result into standardized `research_infra` sidecar artifacts.

**Architecture:** Create `stock_research.research_infra.mid_trend_integration` as a pure adapter over the already-completed method-layer contracts. The adapter accepts a `review_result` dictionary, writes sidecar JSON/Markdown artifacts, and does not import or modify uncommitted mid-trend workflow modules.

**Tech Stack:** Python, pandas, existing `stock_research.research_infra` modules, pytest, JSON/JSONL, Markdown.

---

## File Structure

- Create: `src/stock_research/research_infra/mid_trend_integration.py`
  - Owns mid-trend review-result to research-infra artifact conversion.
  - Depends only on `run_evidence`, `experiment_registry`, `research_signals`, and `attribution_cards`.
- Create: `tests/test_research_infra_mid_trend_integration.py`
  - Tests artifact writing, signal conversion, attribution conversion, empty review behavior, and run-card artifact references.
- Modify: `docs/research-infrastructure-method-migration.md`
  - Adds a short Mid-Trend Integration section and example.

Do not modify `src/stock_research/mid_trend_portfolio_review.py` in this slice.

## Task 1: Integration Writes Sidecar Artifacts

**Files:**
- Create: `tests/test_research_infra_mid_trend_integration.py`
- Create: `src/stock_research/research_infra/mid_trend_integration.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.research_infra.mid_trend_integration import (
    write_mid_trend_research_infra_artifacts,
)


def _toy_review_result(tmp_path: Path) -> dict:
    review_csv = tmp_path / "mid_trend_portfolio_review_2026-06-04.csv"
    review_md = tmp_path / "mid_trend_portfolio_review_2026-06-04.md"
    review_csv.write_text("asset_id,final_label\nCN:SH:600183,高优先级持有\n", encoding="utf-8")
    review_md.write_text("# Mid Trend Review\n", encoding="utf-8")
    return {
        "portfolio_summary": {
            "trade_date": "2026-06-04",
            "strategy_variant": "top5_weekly_max_2_replacements",
            "review_count": 2,
        },
        "review_rows": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:600183",
                    "ts_code": "600183.SH",
                    "trade_date": "2026-06-04",
                    "stock_name": "A",
                    "section": "top5",
                    "final_label": "高优先级持有",
                    "research_support_score_pit": 33,
                    "broker_report_count_90d": 3,
                    "pdf_risk_section_count_90d": 3,
                    "market_regime": "mainline",
                    "mainline_status": "sustained_mainline",
                    "why_hold_or_change": "高支持度且为核心持仓，继续持有。",
                },
                {
                    "asset_id": "CN:SZ:300201",
                    "ts_code": "300201.SZ",
                    "trade_date": "2026-06-04",
                    "stock_name": "B",
                    "section": "top5",
                    "final_label": "低优先级持有",
                    "research_support_score_pit": 0,
                    "broker_report_count_90d": 0,
                    "pdf_risk_section_count_90d": 0,
                    "market_regime": "mainline",
                    "mainline_status": "neutral",
                    "why_hold_or_change": "",
                },
            ]
        ),
        "markdown": "# Mid Trend Review\n",
        "paths": {"csv": str(review_csv), "md": str(review_md), "report": str(review_md)},
    }


def test_write_mid_trend_research_infra_artifacts_writes_sidecars(tmp_path: Path) -> None:
    result = write_mid_trend_research_infra_artifacts(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_result=_toy_review_result(tmp_path),
        output_dir=tmp_path,
    )

    sidecar_dir = tmp_path / "research_infra"
    assert Path(result["research_signals_json_path"]).exists()
    assert Path(result["attribution_cards_json_path"]).exists()
    assert Path(result["attribution_cards_md_path"]).exists()
    assert Path(result["experiment_registry_path"]).exists()
    assert Path(result["run_card"]["run_card_json_path"]).exists()
    assert Path(result["run_card"]["run_card_json_path"]).is_relative_to(sidecar_dir)
    assert result["research_signal_count"] == 6
    assert result["attribution_card_count"] == 1

    signals = json.loads(Path(result["research_signals_json_path"]).read_text(encoding="utf-8"))
    assert {row["signal_name"] for row in signals} == {
        "research_support_score",
        "coverage_freshness_score",
        "risk_disclosure_score",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py::test_write_mid_trend_research_infra_artifacts_writes_sidecars -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.research_infra.mid_trend_integration'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/stock_research/research_infra/mid_trend_integration.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.research_infra.attribution_cards import (
    AttributionCard,
    export_attribution_cards,
    render_attribution_card_markdown,
)
from stock_research.research_infra.experiment_registry import (
    ExperimentRecord,
    append_experiment_record,
)
from stock_research.research_infra.research_signals import (
    ResearchSignalRecord,
    export_research_signal_records,
)
from stock_research.research_infra.run_evidence import write_evidence_bundle


def write_mid_trend_research_infra_artifacts(
    *,
    trade_date: str,
    strategy_variant: str,
    review_result: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    sidecar_dir = Path(output_dir) / "research_infra"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    review_rows = _review_rows(review_result)

    signals = _build_signals(review_rows, trade_date)
    attributions = _build_attributions(review_rows, trade_date, strategy_variant)

    signals_path = sidecar_dir / "research_signals.json"
    attributions_json_path = sidecar_dir / "attribution_cards.json"
    attributions_md_path = sidecar_dir / "attribution_cards.md"
    experiment_registry_path = sidecar_dir / "experiment_registry.jsonl"

    signals_path.write_text(
        json.dumps(export_research_signal_records(signals), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    attributions_json_path.write_text(
        json.dumps(export_attribution_cards(attributions), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    attributions_md_path.write_text(
        "\n\n".join(render_attribution_card_markdown(card) for card in attributions) + ("\n" if attributions else ""),
        encoding="utf-8",
    )

    run_card = write_evidence_bundle(
        output_dir=sidecar_dir / "run_card",
        run_type="mid_trend_portfolio_review",
        run_id=f"mid-trend-review-{trade_date}-{strategy_variant}",
        title=f"Mid-Trend Portfolio Review {trade_date}",
        research_question="Should current mid-trend candidates be held, deprioritized, or discussed?",
        sample_window={"start_date": trade_date, "end_date": trade_date},
        universe={"strategy_variant": strategy_variant, "review_row_count": int(len(review_rows))},
        feature_set=[
            "research_support_score",
            "coverage_freshness_score",
            "risk_disclosure_score",
            "market_regime",
            "mainline_status",
            "final_label",
        ],
        label_definition={"name": "mid_trend_review_final_label", "source": "review_rows.final_label"},
        input_artifacts={},
        output_artifacts={
            **{str(key): str(value) for key, value in (review_result.get("paths") or {}).items()},
            "research_signals": str(signals_path),
            "attribution_cards_json": str(attributions_json_path),
            "attribution_cards_markdown": str(attributions_md_path),
        },
        metrics={
            "review_row_count": int(len(review_rows)),
            "research_signal_count": len(signals),
            "attribution_card_count": len(attributions),
        },
        warnings=[] if not review_rows.empty else ["empty_review_rows"],
        caveats=["review-only; no execution instruction"],
        reuse_status="monitor_only",
    )

    append_experiment_record(
        experiment_registry_path,
        ExperimentRecord(
            experiment_id=f"mid-trend-review-infra-{trade_date}-{strategy_variant}",
            created_at=f"{trade_date}T15:00:00",
            objective="Standardize evidence for mid-trend review.",
            hypothesis="Standardized evidence improves review reproducibility and coverage-gap diagnosis.",
            sample_window={"start_date": trade_date, "end_date": trade_date},
            universe={"strategy_variant": strategy_variant, "review_row_count": int(len(review_rows))},
            feature_set_id="feature-set:mid-trend-review-infra-v1",
            label_id="label:mid-trend-review-final-label",
            model_or_rule_version="mid_trend_research_infra_integration_v1",
            constraints={"review_only": True},
            artifact_paths={
                "run_card": run_card["run_card_json_path"],
                "research_signals": str(signals_path),
                "attribution_cards_json": str(attributions_json_path),
            },
            conclusion="Monitor-only integration artifact.",
            reuse_status="monitor_only",
        ),
    )

    return {
        "research_infra_dir": str(sidecar_dir),
        "research_signals_json_path": str(signals_path),
        "attribution_cards_json_path": str(attributions_json_path),
        "attribution_cards_md_path": str(attributions_md_path),
        "experiment_registry_path": str(experiment_registry_path),
        "run_card": run_card,
        "research_signal_count": len(signals),
        "attribution_card_count": len(attributions),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py::test_write_mid_trend_research_infra_artifacts_writes_sidecars -q
```

Expected: PASS.

## Task 2: Signal and Attribution Helpers

**Files:**
- Modify: `src/stock_research/research_infra/mid_trend_integration.py`
- Test: `tests/test_research_infra_mid_trend_integration.py`

- [ ] **Step 1: Add failing tests for missingness and coverage-gap attribution**

Append:

```python
def test_mid_trend_integration_distinguishes_missing_coverage(tmp_path: Path) -> None:
    result = write_mid_trend_research_infra_artifacts(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_result=_toy_review_result(tmp_path),
        output_dir=tmp_path,
    )

    signals = json.loads(Path(result["research_signals_json_path"]).read_text(encoding="utf-8"))
    by_asset_signal = {(row["asset_id"], row["signal_name"]): row for row in signals}
    missing = by_asset_signal[("CN:SZ:300201", "coverage_freshness_score")]
    assert missing["signal_value"] is None
    assert missing["missingness_reason"] == "no_fresh_report"

    cards = json.loads(Path(result["attribution_cards_json_path"]).read_text(encoding="utf-8"))
    assert cards[0]["primary_cause"] == "research_coverage_gap"
    assert cards[0]["evidence"]["broker_report_count_90d"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py::test_mid_trend_integration_distinguishes_missing_coverage -q
```

Expected: FAIL until helper mapping is implemented.

- [ ] **Step 3: Implement helper functions**

Add to `mid_trend_integration.py`:

```python
def _review_rows(review_result: dict[str, Any]) -> pd.DataFrame:
    rows = review_result.get("review_rows")
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    return pd.DataFrame()


def _build_signals(review_rows: pd.DataFrame, trade_date: str) -> list[ResearchSignalRecord]:
    signals: list[ResearchSignalRecord] = []
    available_at = f"{trade_date}T15:00:00"
    for _, row in review_rows.iterrows():
        asset_id = str(row.get("asset_id", ""))
        ts_code = str(row.get("ts_code", ""))
        report_count = _int_or_zero(row.get("broker_report_count_90d"))
        risk_count = _int_or_zero(row.get("pdf_risk_section_count_90d"))
        support = _float_or_none(row.get("research_support_score_pit"))
        has_fresh_report = report_count > 0
        signal_specs = [
            ("research_support_score", support if has_fresh_report else None),
            ("coverage_freshness_score", float(report_count) if has_fresh_report else None),
            ("risk_disclosure_score", float(risk_count) if risk_count > 0 else None),
        ]
        for signal_name, value in signal_specs:
            signals.append(
                ResearchSignalRecord(
                    asset_id=asset_id,
                    ts_code=ts_code,
                    trade_date=trade_date,
                    signal_name=signal_name,
                    signal_value=value,
                    signal_type="numeric",
                    source_type="manual_review",
                    source_id=f"mid_trend_review:{trade_date}:{asset_id}",
                    availability_timestamp=available_at,
                    confidence="medium" if has_fresh_report else "thin",
                    missingness_reason="" if value is not None else "no_fresh_report",
                )
            )
    return signals


def _build_attributions(
    review_rows: pd.DataFrame,
    trade_date: str,
    strategy_variant: str,
) -> list[AttributionCard]:
    cards: list[AttributionCard] = []
    for _, row in review_rows.iterrows():
        report_count = _int_or_zero(row.get("broker_report_count_90d"))
        final_label = str(row.get("final_label", ""))
        if report_count > 0 or "低优先级" not in final_label:
            continue
        asset_id = str(row.get("asset_id", ""))
        cards.append(
            AttributionCard(
                case_id=f"case:mid-trend:{asset_id}:{trade_date}:coverage-gap",
                asset_id=asset_id,
                ts_code=str(row.get("ts_code", "")),
                trade_date=trade_date,
                strategy_context=strategy_variant,
                failure_or_success_type="mixed",
                primary_cause="research_coverage_gap",
                secondary_causes=[],
                evidence={
                    "final_label": final_label,
                    "broker_report_count_90d": report_count,
                    "research_support_score_pit": _float_or_none(row.get("research_support_score_pit")),
                },
                counterfactual="Require fresh research coverage before high-priority hold review.",
                preventability="partly_preventable",
                recommended_rule_change="Flag low-priority holds with no fresh report coverage.",
                confidence="medium",
            )
        )
    return cards


def _int_or_zero(value: Any) -> int:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return 0
    return int(parsed)


def _float_or_none(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return float(parsed)
```

- [ ] **Step 4: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py -q
```

Expected: PASS.

## Task 3: Empty Review Rows and Documentation

**Files:**
- Modify: `tests/test_research_infra_mid_trend_integration.py`
- Modify: `docs/research-infrastructure-method-migration.md`

- [ ] **Step 1: Add failing empty-review test**

Append:

```python
def test_mid_trend_integration_handles_empty_review_rows(tmp_path: Path) -> None:
    result = write_mid_trend_research_infra_artifacts(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_result={
            "portfolio_summary": {"trade_date": "2026-06-04"},
            "review_rows": pd.DataFrame(),
            "markdown": "",
            "paths": {},
        },
        output_dir=tmp_path,
    )

    assert result["research_signal_count"] == 0
    assert result["attribution_card_count"] == 0
    run_card = json.loads(Path(result["run_card"]["run_card_json_path"]).read_text(encoding="utf-8"))
    assert "empty_review_rows" in run_card["warnings"]
```

- [ ] **Step 2: Run empty-review test**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py::test_mid_trend_integration_handles_empty_review_rows -q
```

Expected: PASS if Task 1 implementation already writes warnings for empty rows.

- [ ] **Step 3: Update docs**

Add a `Mid-Trend Integration` section to `docs/research-infrastructure-method-migration.md`:

```markdown
## Mid-Trend Integration

Use `write_mid_trend_research_infra_artifacts()` after an existing mid-trend
portfolio review has produced `review_result`. The integration writes sidecar
artifacts under `<output_dir>/research_infra/` and does not change review rows,
portfolio logic, or execution behavior.
```

- [ ] **Step 4: Run focused docs-adjacent tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py -q
```

Expected: PASS.

## Task 4: Full Focused Verification and Commit

**Files:**
- All files above.

- [ ] **Step 1: Run focused verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_run_card.py \
  tests/test_factor_eval.py \
  tests/test_research_infra_run_evidence.py \
  tests/test_research_infra_experiment_registry.py \
  tests/test_research_infra_feature_registry.py \
  tests/test_research_infra_research_signals.py \
  tests/test_research_infra_factor_cards.py \
  tests/test_research_infra_attribution_cards.py \
  tests/test_research_infra_mid_trend_integration.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Commit**

```bash
git add \
  docs/research-infrastructure-method-migration.md \
  src/stock_research/research_infra/mid_trend_integration.py \
  tests/test_research_infra_mid_trend_integration.py
git commit -m "feat: add mid-trend research infra integration"
```

## Self-Review

- Spec coverage: The plan implements a thin adapter, sidecar artifacts, run evidence, experiment record, research signals, attribution cards, empty-review handling, and review-only boundaries.
- Placeholder scan: No implementation placeholders remain; the code snippets define concrete APIs and expected behavior.
- Type consistency: The plan uses `write_mid_trend_research_infra_artifacts()` consistently across tests and implementation.
- Scope check: The plan does not modify `mid_trend_portfolio_review.py` and does not depend on uncommitted mid-trend modules.
