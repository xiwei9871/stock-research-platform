# Strategy Score Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a non-blocking audit chain that records raw score, published score, display score, and anomaly flags for the three official EOD strategies, then expose the results through CLI and dashboard surfaces.

**Architecture:** Add a dedicated audit builder module that normalizes per-strategy score lineage into a single artifact set under `outputs/research/strategy_daily_eod/<trade_date>/`. Integrate audit generation into `strategy_eod_publish`, expose read-only audit summary APIs in the dashboard backend, and surface score provenance plus anomaly counts in the UI without changing readiness gating.

**Tech Stack:** Python, pandas, FastAPI, pytest, React, TypeScript, Vite

---

### Task 1: Build The Audit Core

**Files:**
- Create: `src/stock_research/strategy_score_audit.py`
- Modify: `tests/test_strategy_eod_publish.py`
- Create: `tests/test_strategy_score_audit.py`

- [ ] **Step 1: Write the failing audit-core tests**

```python
from stock_research.strategy_score_audit import (
    build_strategy_score_audit,
    summarize_strategy_score_audit,
)


def test_lhb_audit_flags_mapped_score_without_raw_score() -> None:
    review_rows = [
        {
            "trade_date": "2026-06-22",
            "asset_id": "000960.SZ",
            "rank": 1,
            "score_total": 20.0,
            "score_source": "auction_enhanced_score",
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "strategy_run_id": "strategy-eod-2026-06-22-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_lhb_shortline",
            "source_rank": 1,
            "review_tier": "top5_focus",
        }
    ]
    strategy_results = {
        "lhb_shortline": {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "candidates": [
                {
                    "trade_date": "2026-06-22",
                    "ts_code": "000960.SZ",
                    "phase12a_rule_layer": "pending_intraday",
                    "candidate_reason": "lhb_capital_plus_structure",
                    "auction_enhanced_score": 20.0,
                }
            ],
        }
    }

    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )

    row = detail.iloc[0].to_dict()
    assert row["raw_candidate_score"] is None
    assert "mapped_score_without_raw_score" in row["anomaly_flags"]
    assert row["eligibility_layer"] == "pending_intraday"


def test_tech_audit_tracks_raw_and_scaled_published_scores() -> None:
    review_rows = [
        {
            "trade_date": "2026-06-22",
            "asset_id": "CN:SZ:300408",
            "rank": 1,
            "score_total": 63.46,
            "score_source": "bottleneck_score",
            "strategy_id": "tech_bottleneck",
            "strategy_name": "Tech Bottleneck Discovery",
            "strategy_run_id": "strategy-eod-2026-06-22-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_tech_bottleneck",
            "source_rank": 1,
            "review_tier": "top5_focus",
        }
    ]
    strategy_results = {
        "tech_bottleneck": {
            "review_rows": [
                {
                    "trade_date": "2026-06-22",
                    "asset_id": "CN:SZ:300408",
                    "rank": 1,
                    "bottleneck_score": 0.6346,
                    "stock_name": "三环集团",
                }
            ]
        }
    }

    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )

    row = detail.iloc[0].to_dict()
    assert row["raw_candidate_score"] == 0.6346
    assert row["raw_candidate_score_source"] == "bottleneck_score"
    assert row["published_score"] == 63.46
    assert row["published_score_source"] == "bottleneck_score_x100"
    assert row["anomaly_flags"] == []
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_strategy_score_audit.py
```

Expected: FAIL with `ModuleNotFoundError` or missing symbol errors for `strategy_score_audit`.

- [ ] **Step 3: Implement the audit builder module**

```python
# src/stock_research/strategy_score_audit.py
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


DETAIL_COLUMNS = [
    "trade_date",
    "strategy_id",
    "strategy_name",
    "asset_id",
    "stock_name",
    "selected_flag",
    "selected_rank",
    "source_rank",
    "raw_candidate_score",
    "raw_candidate_score_source",
    "published_score",
    "published_score_source",
    "display_score",
    "display_score_source",
    "selection_reason",
    "eligibility_layer",
    "filter_reason",
    "data_date_used",
    "review_tier",
    "source_type",
    "strategy_run_id",
    "anomaly_flags",
    "notes",
]


def build_strategy_score_audit(
    *,
    trade_date: str,
    review_rows: list[dict[str, Any]],
    strategy_results: dict[str, dict[str, Any]],
    display_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    display_lookup = _display_row_lookup(display_rows)
    for review_row in review_rows:
        strategy_id = str(review_row.get("strategy_id") or "")
        strategy_result = strategy_results.get(strategy_id) or {}
        row = _build_audit_row(
            trade_date=trade_date,
            review_row=review_row,
            strategy_result=strategy_result,
            display_row=display_lookup.get(_row_key(trade_date, review_row.get("asset_id"))),
        )
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=DETAIL_COLUMNS)


def summarize_strategy_score_audit(detail: pd.DataFrame, *, trade_date: str) -> dict[str, Any]:
    anomaly_counter: Counter[str] = Counter()
    strategy_summaries: list[dict[str, Any]] = []
    if detail.empty:
        return {
            "trade_date": trade_date,
            "generated_at": "",
            "strategies": [],
            "total_rows": 0,
            "selected_rows": 0,
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
            "strategy_counts": {},
        }
    for flags in detail["anomaly_flags"]:
        for flag in flags or []:
            anomaly_counter[str(flag)] += 1
    for strategy_id, group in detail.groupby("strategy_id", dropna=False):
        strategy_summaries.append(
            {
                "strategy_id": str(strategy_id or ""),
                "row_count": int(len(group)),
                "selected_count": int(group["selected_flag"].fillna(False).astype(bool).sum()),
                "anomaly_count": int(group["anomaly_flags"].map(lambda values: len(values or []) > 0).sum()),
                "published_score_sources": sorted({str(v) for v in group["published_score_source"].dropna() if str(v)}),
                "display_score_sources": sorted({str(v) for v in group["display_score_source"].dropna() if str(v)}),
                "raw_score_sources": sorted({str(v) for v in group["raw_candidate_score_source"].dropna() if str(v)}),
                "sample_anomalies": group[group["anomaly_flags"].map(bool)].head(3)[["asset_id", "anomaly_flags"]].to_dict("records"),
            }
        )
    return {
        "trade_date": trade_date,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "strategies": strategy_summaries,
        "total_rows": int(len(detail)),
        "selected_rows": int(detail["selected_flag"].fillna(False).astype(bool).sum()),
        "anomaly_row_count": int(detail["anomaly_flags"].map(bool).sum()),
        "anomaly_counts_by_type": dict(sorted(anomaly_counter.items())),
        "strategy_counts": {item["strategy_id"]: item["row_count"] for item in strategy_summaries},
    }
```

- [ ] **Step 4: Run the focused tests to verify the audit core passes**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_strategy_score_audit.py
```

Expected: PASS

- [ ] **Step 5: Commit the audit-core slice**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add src/stock_research/strategy_score_audit.py tests/test_strategy_score_audit.py tests/test_strategy_eod_publish.py
git commit -m "feat: add strategy score audit core"
```

### Task 2: Integrate Audit Output Into EOD Publish And CLI

**Files:**
- Modify: `src/stock_research/strategy_eod_publish.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_strategy_eod_publish.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing integration tests for artifact generation and CLI**

```python
def test_strategy_eod_publish_writes_score_audit_artifacts(tmp_path, monkeypatch) -> None:
    trade_date = "2026-06-22"
    output_dir = tmp_path / trade_date
    review_rows = [
        {
            "trade_date": trade_date,
            "asset_id": "CN:SZ:300951",
            "rank": 1,
            "score_total": 91.2,
            "score_source": "mid_trend_funnel_score",
            "score_explanation": "真实策略输出分；无策略分字段时留空，不使用排名占位分",
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Combo",
            "strategy_run_id": f"strategy-eod-{trade_date}-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_mid_trend",
            "source_rank": 1,
            "review_tier": "top5_focus",
        }
    ]
    monkeypatch.setattr(strategy_eod_publish, "_write_review_queue", lambda frames, output_dir: (output_dir / "review_queue_strategy_manifest.csv", review_rows))
    monkeypatch.setattr(
        strategy_eod_publish,
        "write_strategy_score_audit_outputs",
        lambda **kwargs: {
            "detail_path": str(output_dir / "strategy_score_audit_detail.csv"),
            "summary_path": str(output_dir / "strategy_score_audit_summary.json"),
            "report_path": str(output_dir / "strategy_score_audit_report.md"),
        },
    )

    result = strategy_eod_publish._build_publish_summary(
        trade_date=trade_date,
        output_dir=output_dir,
        review_rows=review_rows,
        strategy_results={"mid_trend": {"strategy_id": "mid_trend"}},
    )

    assert result["audit_paths"]["detail_path"].endswith("strategy_score_audit_detail.csv")


def test_cli_strategy_score_audit_prints_summary(monkeypatch, capsys, tmp_path) -> None:
    summary_path = tmp_path / "strategy_score_audit_summary.json"
    summary_path.write_text(
        '{"trade_date":"2026-06-22","generated_at":"2026-06-23T00:00:00+00:00","strategies":[{"strategy_id":"lhb_shortline","row_count":5,"selected_count":5,"anomaly_count":5,"published_score_sources":["auction_enhanced_score"],"display_score_sources":["auction_enhanced_score"],"raw_score_sources":[],"sample_anomalies":[{"asset_id":"000960.SZ","anomaly_flags":["mapped_score_without_raw_score"]}]}],"total_rows":5,"selected_rows":5,"anomaly_row_count":5,"anomaly_counts_by_type":{"mapped_score_without_raw_score":5},"strategy_counts":{"lhb_shortline":5}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "load_strategy_score_audit_summary", lambda trade_date: json.loads(summary_path.read_text(encoding="utf-8")))

    cli.main(["stock-research", "strategy-score-audit", "--trade-date", "2026-06-22"])

    out = capsys.readouterr().out
    assert "strategy_score_audit|trade_date|2026-06-22" in out
    assert "strategy_score_audit|strategy|lhb_shortline|rows|5|anomalies|5" in out
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_strategy_eod_publish.py tests/test_factor_cli.py -k "score_audit or strategy_score_audit"
```

Expected: FAIL with missing audit helper or missing CLI command errors.

- [ ] **Step 3: Integrate audit output writing into the EOD publisher and CLI**

```python
# src/stock_research/strategy_eod_publish.py
from stock_research.strategy_score_audit import write_strategy_score_audit_outputs


def _write_strategy_score_audit(
    *,
    trade_date: str,
    output_dir: Path,
    review_rows: list[dict[str, Any]],
    strategy_results: dict[str, dict[str, Any]],
) -> dict[str, str]:
    return write_strategy_score_audit_outputs(
        trade_date=trade_date,
        output_dir=output_dir,
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )


# src/stock_research/cli.py
def _run_strategy_score_audit(args) -> int:
    summary = load_strategy_score_audit_summary(trade_date=str(args.trade_date))
    print(f"strategy_score_audit|trade_date|{summary['trade_date']}|rows|{summary['total_rows']}|anomaly_rows|{summary['anomaly_row_count']}")
    for strategy in summary.get("strategies", []):
        print(
            "strategy_score_audit|strategy|{strategy_id}|rows|{row_count}|anomalies|{anomaly_count}|published_sources|{published}".format(
                strategy_id=strategy["strategy_id"],
                row_count=strategy["row_count"],
                anomaly_count=strategy["anomaly_count"],
                published=",".join(strategy.get("published_score_sources") or []),
            )
        )
    return 0


strategy_score_audit_parser = subparsers.add_parser("strategy-score-audit")
strategy_score_audit_parser.add_argument("--trade-date", required=True)
strategy_score_audit_parser.add_argument("--strategy-id")
strategy_score_audit_parser.add_argument("--anomalies-only", action="store_true")
strategy_score_audit_parser.add_argument("--limit", type=int, default=20)
strategy_score_audit_parser.set_defaults(func=_run_strategy_score_audit)
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_strategy_eod_publish.py tests/test_factor_cli.py -k "score_audit or strategy_score_audit"
```

Expected: PASS

- [ ] **Step 5: Commit the integration slice**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add src/stock_research/strategy_eod_publish.py src/stock_research/cli.py tests/test_strategy_eod_publish.py tests/test_factor_cli.py
git commit -m "feat: publish strategy score audit artifacts"
```

### Task 3: Add Dashboard Backend Read APIs

**Files:**
- Create: `src/stock_research/dashboard/strategy_score_audit.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`
- Create: `tests/test_dashboard_strategy_score_audit.py`

- [ ] **Step 1: Write the failing backend API tests**

```python
from fastapi.testclient import TestClient

from stock_research.dashboard.app import create_app


def test_strategy_score_audit_api_returns_warning_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "stock_research.dashboard.strategy_score_audit.load_strategy_score_audit_payload",
        lambda trade_date: {
            "trade_date": trade_date,
            "generated_at": "2026-06-23T00:00:00+00:00",
            "overall_status": "warning",
            "total_rows": 5,
            "anomaly_row_count": 5,
            "anomaly_counts_by_type": {"mapped_score_without_raw_score": 5},
            "strategies": [{"strategy_id": "lhb_shortline", "anomaly_count": 5}],
            "sample_rows": [{"asset_id": "000960.SZ", "anomaly_flags": ["mapped_score_without_raw_score"]}],
        },
    )
    client = TestClient(create_app())

    response = client.get("/api/strategy-score-audit?trade_date=2026-06-22")

    assert response.status_code == 200
    assert response.json()["overall_status"] == "warning"


def test_strategy_score_audit_api_returns_missing_when_artifacts_absent(monkeypatch) -> None:
    monkeypatch.setattr(
        "stock_research.dashboard.strategy_score_audit.load_strategy_score_audit_payload",
        lambda trade_date: {
            "trade_date": trade_date,
            "generated_at": "",
            "overall_status": "missing",
            "total_rows": 0,
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
            "strategies": [],
            "sample_rows": [],
        },
    )
    client = TestClient(create_app())

    response = client.get("/api/strategy-score-audit?trade_date=2026-06-22")

    assert response.status_code == 200
    assert response.json()["overall_status"] == "missing"
```

- [ ] **Step 2: Run the backend tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_dashboard_app.py tests/test_dashboard_strategy_score_audit.py -k "strategy_score_audit"
```

Expected: FAIL because the dashboard audit module or route does not exist.

- [ ] **Step 3: Implement the backend loader and API route**

```python
# src/stock_research/dashboard/strategy_score_audit.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS


def strategy_score_audit_dir(trade_date: str) -> Path:
    return Path(SETTINGS.output_root) / "research" / "strategy_daily_eod" / trade_date


def load_strategy_score_audit_payload(trade_date: str) -> dict[str, Any]:
    summary_path = strategy_score_audit_dir(trade_date) / "strategy_score_audit_summary.json"
    detail_path = strategy_score_audit_dir(trade_date) / "strategy_score_audit_detail.csv"
    if not summary_path.exists():
        return {
            "trade_date": trade_date,
            "generated_at": "",
            "overall_status": "missing",
            "total_rows": 0,
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
            "strategies": [],
            "sample_rows": [],
        }
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["overall_status"] = "warning" if payload.get("anomaly_row_count") else "ok"
    payload["sample_rows"] = payload.get("sample_rows") or []
    payload["detail_path"] = str(detail_path)
    return payload


# src/stock_research/dashboard/app.py
from stock_research.dashboard.strategy_score_audit import load_strategy_score_audit_payload


@app.get("/api/strategy-score-audit")
def strategy_score_audit(trade_date: str):
    return load_strategy_score_audit_payload(trade_date)
```

- [ ] **Step 4: Run the backend tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_dashboard_app.py tests/test_dashboard_strategy_score_audit.py -k "strategy_score_audit"
```

Expected: PASS

- [ ] **Step 5: Commit the backend API slice**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add src/stock_research/dashboard/strategy_score_audit.py src/stock_research/dashboard/app.py tests/test_dashboard_app.py tests/test_dashboard_strategy_score_audit.py
git commit -m "feat: add dashboard strategy score audit api"
```

### Task 4: Add Frontend Audit Visibility

**Files:**
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Create: `dashboard/tests/home-cockpit-score-audit.test.tsx`

- [ ] **Step 1: Write the failing frontend tests**

```tsx
import { render, screen, waitFor } from '@testing-library/react';

import { HomeCockpit } from '../src/components/HomeCockpit';


test('shows strategy score audit warning summary', async () => {
  vi.mock('../src/api/client', async () => {
    const actual = await vi.importActual('../src/api/client');
    return {
      ...actual,
      fetchPlatformReadiness: async () => ({
        status: 'READY',
        mode: 'normal',
        latest_trade_date: '2026-06-22',
        display_trade_date: '2026-06-22',
        warnings: [],
        health_groups: [],
      }),
      fetchPlatformSummary: async () => ({ latest_market_date: '2026-06-22', strategies: [] }),
      fetchStrategyScoreAudit: async () => ({
        trade_date: '2026-06-22',
        overall_status: 'warning',
        anomaly_row_count: 5,
        anomaly_counts_by_type: { mapped_score_without_raw_score: 5 },
        strategies: [{ strategy_id: 'lhb_shortline', anomaly_count: 5 }],
        sample_rows: [],
      }),
    };
  });

  render(<HomeCockpit />);

  await waitFor(() => expect(screen.getByText('策略打分审计')).toBeInTheDocument());
  expect(screen.getByText('5')).toBeInTheDocument();
  expect(screen.getByText('需关注')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
npm test -- --runInBand home-cockpit-score-audit
```

Expected: FAIL because the client function or UI block does not exist.

- [ ] **Step 3: Implement the frontend client/types and UI**

```ts
// dashboard/src/api/types.ts
export interface StrategyScoreAuditSummary {
  trade_date: string;
  overall_status: 'ok' | 'warning' | 'missing';
  anomaly_row_count: number;
  anomaly_counts_by_type: Record<string, number>;
  strategies: Array<{
    strategy_id: string;
    anomaly_count: number;
  }>;
  sample_rows: Array<{
    asset_id: string;
    anomaly_flags: string[];
  }>;
}


// dashboard/src/api/client.ts
export async function fetchStrategyScoreAudit(tradeDate: string): Promise<StrategyScoreAuditSummary> {
  return getJson<StrategyScoreAuditSummary>(`/api/strategy-score-audit?trade_date=${encodeURIComponent(tradeDate)}`);
}


// dashboard/src/components/HomeCockpit.tsx
const [scoreAudit, setScoreAudit] = useState<StrategyScoreAuditSummary | null>(null);

useEffect(() => {
  if (!displayTradeDate || displayTradeDate === '-') return;
  fetchStrategyScoreAudit(displayTradeDate).then(setScoreAudit).catch(() => setScoreAudit(null));
}, [displayTradeDate]);

<article className="metric-card">
  <small>策略打分审计</small>
  <strong className={`readiness-value ${scoreAudit?.overall_status === 'warning' ? 'partial' : 'ready'}`}>
    {scoreAudit?.overall_status === 'warning' ? '需关注' : scoreAudit?.overall_status === 'ok' ? '正常' : '-'}
  </strong>
  <span>{scoreAudit?.anomaly_row_count ?? 0} 条异常</span>
</article>
```

- [ ] **Step 4: Run the frontend tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
npm test -- --runInBand home-cockpit-score-audit app-shell
```

Expected: PASS

- [ ] **Step 5: Commit the frontend slice**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add dashboard/src/api/client.ts dashboard/src/api/types.ts dashboard/src/components/HomeCockpit.tsx dashboard/src/components/ReviewQueueWorkspace.tsx dashboard/src/styles.css dashboard/tests/app-shell.test.tsx dashboard/tests/home-cockpit-score-audit.test.tsx
git commit -m "feat: surface strategy score audit in dashboard"
```

### Task 5: End-To-End Verification And Replay

**Files:**
- Modify: `tests/test_dashboard_deployment_assets.py`
- Optional output refresh: `outputs/research/strategy_daily_eod/2026-06-22/*`

- [ ] **Step 1: Add a failing regression test for release-time audit visibility**

```python
def test_release_checks_include_strategy_score_audit() -> None:
    script = Path("deploy/check_dashboard_release.sh").read_text(encoding="utf-8")
    assert "/api/strategy-score-audit" in script
```

- [ ] **Step 2: Run the regression test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_dashboard_deployment_assets.py -k "strategy_score_audit"
```

Expected: FAIL because the release check does not probe the audit endpoint yet.

- [ ] **Step 3: Update release verification and replay 2026-06-22**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/python -m stock_research.strategy_eod_publish --trade-date 2026-06-22
/Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli strategy-score-audit --trade-date 2026-06-22
curl -s 'http://127.0.0.1:8765/api/strategy-score-audit?trade_date=2026-06-22'
```

Expected:

- EOD rerun succeeds
- CLI prints `mapped_score_without_raw_score` anomalies for LHB
- API returns `overall_status = "warning"` with non-zero anomaly counts

- [ ] **Step 4: Run the full verification suite**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
/Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_strategy_score_audit.py tests/test_strategy_eod_publish.py tests/test_factor_cli.py tests/test_dashboard_app.py tests/test_dashboard_strategy_score_audit.py tests/test_dashboard_deployment_assets.py
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
npm test -- --runInBand app-shell home-cockpit-score-audit
```

Expected: PASS

- [ ] **Step 5: Commit the verification slice**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add tests/test_dashboard_deployment_assets.py deploy/check_dashboard_release.sh
git commit -m "test: verify strategy score audit release checks"
```

## Self-Review

### Spec Coverage

- Audit artifacts: covered by Task 1 and Task 2.
- Non-blocking EOD integration: covered by Task 2.
- CLI visibility: covered by Task 2.
- Dashboard API: covered by Task 3.
- Dashboard surface for anomaly counts and score source: covered by Task 4.
- Replay and LHB `2026-06-22` diagnosis: covered by Task 5.

### Placeholder Scan

- No `TODO`, `TBD`, or “similar to” placeholders remain.
- Every code-changing task contains concrete code snippets.
- Every verification step includes an exact command and expected result.

### Type Consistency

- Audit detail uses `raw_candidate_score`, `published_score`, and `display_score` consistently across tasks.
- Backend and frontend both use `overall_status`, `anomaly_row_count`, `anomaly_counts_by_type`, `strategies`, and `sample_rows`.
- LHB anomaly flag name is consistently `mapped_score_without_raw_score`.
