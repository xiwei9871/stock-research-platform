# Daily Review Lite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated dashboard page that provides structured read-only review of the `Daily Review v1` report package for a selected `trade_date`.

**Architecture:** Add a new read-only backend read model that resolves the latest eligible `daily_review_v1` package from `report.report_run`, maps trusted artifacts into a Lite payload, and serves controlled artifact URLs. Add a separate frontend page that consumes only this Lite view model, renders fixed review sections, and is selected by a lightweight pathname-based root shell without coupling to the existing workbench data loads.

**Tech Stack:** Python 3.11+, FastAPI, psycopg, pytest, TypeScript, React 19, Vite, Vitest, Testing Library.

---

## File Structure

Backend:

- Create: `src/stock_research/dashboard/daily_review_lite.py`
  Purpose: resolve `daily_review_v1` packages from `report.report_run`, scan fallback packages only when needed, classify artifact health, map raw package files into the Lite payload, and resolve controlled artifact downloads.
- Modify: `src/stock_research/dashboard/app.py`
  Purpose: add read-only routes for the Lite payload and artifact streaming, validate `trade_date`, and keep HTTP semantics aligned with the spec.
- Test: `tests/test_dashboard_daily_review_lite.py`
  Purpose: cover resolver, loader, mapper, fallback, failed state, and artifact key safety.
- Modify: `tests/test_dashboard_app.py`
  Purpose: cover Lite route status semantics, invalid `trade_date`, and artifact endpoint behavior.

Frontend:

- Modify: `dashboard/src/api/types.ts`
  Purpose: add the TypeScript view model for the Lite payload and controlled artifact descriptors.
- Modify: `dashboard/src/api/client.ts`
  Purpose: add `fetchDailyReviewLite(tradeDate)` and keep the existing `getJson` error handling style.
- Create: `dashboard/src/pages/DailyReviewLitePage.tsx`
  Purpose: fetch the Lite payload, render fixed review sections, and handle `ready`, `partial`, `empty`, and `failed` states.
- Create: `dashboard/src/components/DailyReviewLiteStrategyCards.tsx`
  Purpose: render the fixed `LHB`, `Mid Trend`, and `Technical Bottleneck` strategy summaries with `top_items`.
- Create: `dashboard/src/components/DailyReviewLiteArtifactLinks.tsx`
  Purpose: render only backend-provided artifact descriptors.
- Create: `dashboard/src/RootApp.tsx`
  Purpose: select `DailyReviewLitePage` for `/daily-review-lite` and preserve the current workbench app for `/`.
- Modify: `dashboard/src/main.tsx`
  Purpose: render `RootApp` instead of hard-wiring `App`.
- Modify: `dashboard/src/styles.css`
  Purpose: add Lite page layout and state styling without disturbing existing workbench styles.
- Modify: `dashboard/tests/client.test.ts`
  Purpose: cover the new API client function.
- Create: `dashboard/tests/daily-review-lite-page.test.tsx`
  Purpose: cover fixed-section rendering and all page states.
- Create: `dashboard/tests/root-app.test.tsx`
  Purpose: cover pathname-based page selection.

## Scope Guardrails

- Keep the page strictly read-only.
- Do not modify `src/stock_research/reports/daily_review_report_workflow.py`.
- Do not accept user-supplied file paths.
- Do not add React Router; use a tiny pathname switch to stay aligned with current frontend simplicity.
- Do not expose raw artifact paths in the API payload.

---

### Task 1: Build the Backend Lite Resolver, Loader, and Mapper

**Files:**
- Create: `src/stock_research/dashboard/daily_review_lite.py`
- Create: `tests/test_dashboard_daily_review_lite.py`

- [ ] **Step 1: Write the failing backend unit tests**

Create `tests/test_dashboard_daily_review_lite.py`:

```python
import json
from pathlib import Path

from stock_research.dashboard import daily_review_lite


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def _write_package(root: Path, *, trade_date: str = "2026-06-20") -> dict[str, object]:
    package_root = root / trade_date
    evidence_root = package_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    daily_review = {
        "trade_date": trade_date,
        "run_id": "daily_review_v1_20260620_2200",
        "report_type": "daily_review_v1",
        "schema_version": "daily_review_v1",
        "status": "partial",
        "market_review": {
            "risk_state": "defensive",
            "target_exposure": "defensive",
            "market_comment": "Stay defensive.",
            "emotion_state": "cold",
            "trend_environment": "retreat",
            "style_bias": "large_cap_defensive",
        },
        "strategy_summaries": {
            "lhb": {
                "conclusion": "trial",
                "short_allowed": True,
                "watch_count": 1,
                "forbidden_actions": ["chase stale LHB names"],
            },
            "mid_trend": {
                "conclusion": "hold core names",
                "portfolio_health": "stable",
                "holding_count": 1,
            },
            "technical_bottleneck": {
                "conclusion": "monitor upgrades only",
                "upgraded_count": 1,
                "research_required_count": 0,
            },
        },
        "strategy_items": [
            {
                "strategy_id": "lhb",
                "asset_id": "CN:SH:600000",
                "stock_name": "浦发银行",
                "action": "manual_review",
                "review_priority": "P0",
                "reason": {"setup": "bank rotation leader"},
            }
        ],
        "holding_reviews": [
            {
                "strategy_id": "lhb",
                "asset_id": "CN:SH:600000",
                "current_state": "watch",
                "action": "manual_review",
                "risk_status": "elevated",
                "exit_condition": "break_open_low",
            }
        ],
        "operator_plan": {
            "mode": "manual_review_only",
            "overall_position_bias": "defensive",
            "must_check_before_open": ["CN:SH:600000"],
            "forbidden_actions": ["chase stale LHB names"],
        },
        "next_day_plan": {
            "must_review_items": [
                {
                    "asset_id": "CN:SH:600000",
                    "ts_code": "600000.SH",
                    "stock_name": "浦发银行",
                    "strategy_ids": ["lhb"],
                    "reasons": [
                        {
                            "strategy_id": "lhb",
                            "reason": {"setup": "bank rotation leader"},
                        }
                    ],
                }
            ]
        },
        "data_readiness": {
            "lhb_feed": {
                "status": "missing",
                "summary": "lhb payload missing for trade date",
                "confidence_impact": "LHB conclusion confidence reduced",
                "blocking_modules": ["lhb_review"],
                "freshness": {
                    "latest_available_date": "2026-06-19",
                    "expected_date": trade_date,
                    "is_fresh": False,
                },
            }
        },
        "warnings": ["source_missing:lhb_feed"],
    }
    manifest = {
        "trade_date": trade_date,
        "run_id": "daily_review_v1_20260620_2200",
        "report_type": "daily_review_v1",
        "status": "partial",
        "report_paths": {},
        "warnings": ["source_missing:lhb_feed"],
    }
    operator_plan_template = {
        "trade_date": trade_date,
        "created_from_run_id": "daily_review_v1_20260620_2200",
        "decision_status": "pending",
        "manual_decisions": [],
    }
    (package_root / "daily_review.json").write_text(json.dumps(daily_review), encoding="utf-8")
    (package_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package_root / "operator_plan_template.json").write_text(
        json.dumps(operator_plan_template), encoding="utf-8"
    )
    (package_root / "daily_review.md").write_text("# Daily Review", encoding="utf-8")
    (evidence_root / "market_state.json").write_text(json.dumps({"risk_state": "defensive"}), encoding="utf-8")
    return {
        "package_root": str(package_root),
        "json_path": str(package_root / "daily_review.json"),
        "markdown_path": str(package_root / "daily_review.md"),
        "manifest_path": str(package_root / "manifest.json"),
        "operator_plan_template_path": str(package_root / "operator_plan_template.json"),
        "evidence_paths": {
            "market_state": str(evidence_root / "market_state.json"),
        },
    }


def test_select_latest_daily_review_run_uses_eligible_report_run_query(monkeypatch):
    captured = {}
    monkeypatch.setattr(daily_review_lite, "connect", lambda service: _Context(object()))
    monkeypatch.setattr(
        daily_review_lite,
        "fetch_all",
        lambda conn, sql, params: captured.update({"sql": sql, "params": params}) or [],
    )

    result = daily_review_lite._select_latest_daily_review_run("2026-06-20")

    assert result is None
    assert "report.report_run" in captured["sql"]
    assert "report_type = %s" in captured["sql"]
    assert "status IN ('success', 'partial')" in captured["sql"]
    assert "ORDER BY updated_at DESC" in captured["sql"]
    assert captured["params"] == ["2026-06-20", "daily_review_v1"]


def test_load_daily_review_lite_returns_empty_when_nothing_matches(monkeypatch, tmp_path):
    monkeypatch.setattr(daily_review_lite, "_select_latest_daily_review_run", lambda trade_date, service=None: None)
    monkeypatch.setattr(daily_review_lite, "_scan_fallback_package", lambda trade_date, root=None: None)

    result = daily_review_lite.load_daily_review_lite("2026-06-20", fallback_root=tmp_path)

    assert result["state"] == "empty"
    assert result["selected_run"] is None
    assert result["artifacts"] == []


def test_load_daily_review_lite_maps_partial_payload_from_report_run(monkeypatch, tmp_path):
    report_paths = _write_package(tmp_path)
    monkeypatch.setattr(
        daily_review_lite,
        "_select_latest_daily_review_run",
        lambda trade_date, service=None: {
            "run_id": "daily_review_v1:2026-06-20:abc123",
            "trade_date": trade_date,
            "report_type": "daily_review_v1",
            "status": "partial",
            "updated_at": "2026-06-20T22:05:00+08:00",
            "report_paths": report_paths,
        },
    )

    result = daily_review_lite.load_daily_review_lite("2026-06-20", fallback_root=tmp_path)

    assert result["state"] == "partial"
    assert result["selected_run"]["source"] == "report_run"
    assert result["selected_run"]["artifact_health"] == "healthy"
    assert result["selected_run"]["artifact_health_detail"]["daily_review_json"] == "healthy"
    assert result["sections"]["strategy_summaries"]["lhb"]["top_items"][0]["asset_id"] == "CN:SH:600000"
    assert result["sections"]["next_day_checklist"]["must_review_items"][0]["reasons"][0]["summary"] == "bank rotation leader"
    assert all("path" not in artifact for artifact in result["artifacts"])


def test_load_daily_review_lite_marks_fallback_source(monkeypatch, tmp_path):
    report_paths = _write_package(tmp_path)
    monkeypatch.setattr(daily_review_lite, "_select_latest_daily_review_run", lambda trade_date, service=None: None)
    monkeypatch.setattr(
        daily_review_lite,
        "_scan_fallback_package",
        lambda trade_date, root=None: {
            "run_id": f"fallback:{trade_date}",
            "trade_date": trade_date,
            "report_type": "daily_review_v1",
            "status": "partial",
            "updated_at": "",
            "report_paths": report_paths,
        },
    )

    result = daily_review_lite.load_daily_review_lite("2026-06-20", fallback_root=tmp_path)

    assert result["selected_run"]["source"] == "fallback"


def test_load_daily_review_lite_returns_failed_when_core_artifact_is_missing(monkeypatch, tmp_path):
    package_root = tmp_path / "2026-06-20"
    package_root.mkdir(parents=True)
    monkeypatch.setattr(
        daily_review_lite,
        "_select_latest_daily_review_run",
        lambda trade_date, service=None: {
            "run_id": "daily_review_v1:2026-06-20:missing",
            "trade_date": trade_date,
            "report_type": "daily_review_v1",
            "status": "success",
            "updated_at": "2026-06-20T22:05:00+08:00",
            "report_paths": {
                "package_root": str(package_root),
                "json_path": str(package_root / "daily_review.json"),
            },
        },
    )

    result = daily_review_lite.load_daily_review_lite("2026-06-20", fallback_root=tmp_path)

    assert result["state"] == "failed"
    assert result["selected_run"]["artifact_health"] == "missing"
    assert result["selected_run"]["artifact_health_detail"]["daily_review_json"] == "missing"


def test_resolve_daily_review_lite_artifact_rejects_unknown_key(monkeypatch, tmp_path):
    report_paths = _write_package(tmp_path)
    monkeypatch.setattr(
        daily_review_lite,
        "_select_latest_daily_review_run",
        lambda trade_date, service=None: {
            "run_id": "daily_review_v1:2026-06-20:abc123",
            "trade_date": trade_date,
            "report_type": "daily_review_v1",
            "status": "partial",
            "updated_at": "2026-06-20T22:05:00+08:00",
            "report_paths": report_paths,
        },
    )

    assert daily_review_lite.resolve_daily_review_lite_artifact(
        "2026-06-20",
        key="not_registered",
        run_id="daily_review_v1:2026-06-20:abc123",
        fallback_root=tmp_path,
    ) is None
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_daily_review_lite.py -q
```

Expected: FAIL because `stock_research.dashboard.daily_review_lite` does not exist.

- [ ] **Step 3: Implement the resolver, loader, mapper, and artifact registry**

Create `src/stock_research/dashboard/daily_review_lite.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


REPORT_TYPE = "daily_review_v1"
DEFAULT_FALLBACK_ROOT = Path("/Users/xiwei/stock_research/reports/daily_review")
CORE_ARTIFACT_KEYS = {
    "daily_review_json": ("json_path", "Daily Review JSON", "json"),
    "daily_review_markdown": ("markdown_path", "Daily Review Markdown", "markdown"),
    "manifest_json": ("manifest_path", "Manifest JSON", "manifest"),
    "operator_plan_template_json": (
        "operator_plan_template_path",
        "Operator Plan Template",
        "operator_plan",
    ),
}


def load_daily_review_lite(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
    fallback_root: str | Path | None = None,
) -> dict[str, Any]:
    selected = _select_latest_daily_review_run(trade_date, service=service)
    source = "report_run"
    if selected is None:
        selected = _scan_fallback_package(trade_date, root=fallback_root or DEFAULT_FALLBACK_ROOT)
        source = "fallback" if selected is not None else "report_run"
    if selected is None:
        return {
            "trade_date": trade_date,
            "state": "empty",
            "selected_run": None,
            "summary": None,
            "warnings": [],
            "missing_sources": [],
            "sections": {},
            "artifacts": [],
        }

    artifact_health, artifact_health_detail, loaded = _load_registered_artifacts(selected["report_paths"])
    selected_run = {
        "run_id": str(selected["run_id"]),
        "report_type": REPORT_TYPE,
        "status": str(selected.get("status") or ""),
        "updated_at": str(selected.get("updated_at") or ""),
        "source": source,
        "artifact_health": artifact_health,
        "artifact_health_detail": artifact_health_detail,
    }
    daily_review = loaded.get("daily_review_json")
    if not isinstance(daily_review, dict):
        return {
            "trade_date": trade_date,
            "state": "failed",
            "selected_run": selected_run,
            "summary": None,
            "warnings": ["daily_review_json_unavailable"],
            "missing_sources": [],
            "sections": {},
            "artifacts": _build_artifacts(trade_date, selected_run["run_id"], selected["report_paths"]),
        }

    return _map_daily_review_lite(
        trade_date=trade_date,
        selected_run=selected_run,
        daily_review=daily_review,
        manifest=loaded.get("manifest_json") if isinstance(loaded.get("manifest_json"), dict) else {},
        operator_plan_template=(
            loaded.get("operator_plan_template_json")
            if isinstance(loaded.get("operator_plan_template_json"), dict)
            else {}
        ),
        report_paths=selected["report_paths"],
    )


def resolve_daily_review_lite_artifact(
    trade_date: str,
    *,
    key: str,
    run_id: str | None = None,
    service: str = SETTINGS.research_service,
    fallback_root: str | Path | None = None,
) -> dict[str, str] | None:
    selected = _select_latest_daily_review_run(trade_date, service=service)
    if selected is None or (run_id and str(selected["run_id"]) != run_id):
        selected = _scan_fallback_package(trade_date, root=fallback_root or DEFAULT_FALLBACK_ROOT)
    if selected is None:
        return None
    registry = _artifact_registry(selected["report_paths"])
    artifact = registry.get(key)
    if artifact is None:
        return None
    path = Path(artifact["path"])
    if not path.exists() or not path.is_file():
        return None
    return {"path": str(path), "filename": path.name, "media_type": _media_type_for(artifact["kind"])}


def _select_latest_daily_review_run(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT run_id, trade_date::text AS trade_date, report_type, status, report_paths, updated_at::text AS updated_at
    FROM report.report_run
    WHERE trade_date = %s
      AND report_type = %s
      AND status IN ('success', 'partial')
    ORDER BY updated_at DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, REPORT_TYPE])
    if not rows:
        return None
    row = rows[0]
    report_paths = row.get("report_paths")
    if isinstance(report_paths, str):
        report_paths = json.loads(report_paths)
    return {
        "run_id": str(row["run_id"]),
        "trade_date": str(row["trade_date"]),
        "report_type": str(row["report_type"]),
        "status": str(row["status"]),
        "updated_at": str(row.get("updated_at") or ""),
        "report_paths": report_paths if isinstance(report_paths, dict) else {},
    }


def _scan_fallback_package(trade_date: str, *, root: str | Path) -> dict[str, Any] | None:
    package_root = Path(root) / trade_date
    if not package_root.exists():
        return None
    report_paths = {
        "package_root": str(package_root),
        "json_path": str(package_root / "daily_review.json"),
        "markdown_path": str(package_root / "daily_review.md"),
        "manifest_path": str(package_root / "manifest.json"),
        "operator_plan_template_path": str(package_root / "operator_plan_template.json"),
        "evidence_paths": {
            "market_state": str(package_root / "evidence" / "market_state.json"),
        },
    }
    return {
        "run_id": f"fallback:{trade_date}",
        "trade_date": trade_date,
        "report_type": REPORT_TYPE,
        "status": "partial",
        "updated_at": "",
        "report_paths": report_paths,
    }


def _load_registered_artifacts(report_paths: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any]]:
    loaded: dict[str, Any] = {}
    health = "healthy"
    detail: dict[str, str] = {}
    for key, artifact in _artifact_registry(report_paths).items():
        path = Path(artifact["path"])
        if not path.exists():
            detail[key] = "missing"
            if key == "daily_review_json":
                health = "missing"
            continue
        try:
            if artifact["kind"] in {"json", "manifest", "operator_plan"}:
                loaded[key] = json.loads(path.read_text(encoding="utf-8"))
            else:
                loaded[key] = path.read_text(encoding="utf-8")
            detail[key] = "healthy"
        except json.JSONDecodeError:
            detail[key] = "invalid"
            if key == "daily_review_json":
                health = "invalid"
    return health, detail, loaded


def _artifact_registry(report_paths: dict[str, Any]) -> dict[str, dict[str, str]]:
    registry: dict[str, dict[str, str]] = {}
    for key, (path_key, label, kind) in CORE_ARTIFACT_KEYS.items():
        path = report_paths.get(path_key)
        if isinstance(path, str) and path:
            registry[key] = {"path": path, "label": label, "kind": kind}
    for evidence_key, path in (report_paths.get("evidence_paths") or {}).items():
        if isinstance(path, str) and path:
            registry[f"evidence_{evidence_key}"] = {
                "path": path,
                "label": evidence_key.replace("_", " ").title(),
                "kind": "evidence",
            }
    return registry


def _build_artifacts(trade_date: str, run_id: str, report_paths: dict[str, Any]) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for key, item in _artifact_registry(report_paths).items():
        artifacts.append(
            {
                "key": key,
                "label": item["label"],
                "kind": item["kind"],
                "url": (
                    f"/api/daily-review-lite/artifacts?trade_date={trade_date}"
                    f"&key={key}&run_id={run_id}"
                ),
            }
        )
    return artifacts


def _map_daily_review_lite(
    *,
    trade_date: str,
    selected_run: dict[str, Any],
    daily_review: dict[str, Any],
    manifest: dict[str, Any],
    operator_plan_template: dict[str, Any],
    report_paths: dict[str, Any],
) -> dict[str, Any]:
    warnings = [str(item) for item in daily_review.get("warnings") or []]
    missing_sources = []
    data_items = []
    for source_key, item in (daily_review.get("data_readiness") or {}).items():
        status = str(item.get("status") or "")
        affected_sections = _affected_sections_for(source_key, item)
        if status and status != "ready":
            missing_sources.append(
                {
                    "source_key": source_key,
                    "summary": str(item.get("summary") or ""),
                    "affected_sections": affected_sections,
                    "confidence_impact": str(item.get("confidence_impact") or ""),
                }
            )
        freshness = item.get("freshness") or {}
        data_items.append(
            {
                "source_key": source_key,
                "status": status,
                "summary": str(item.get("summary") or ""),
                "freshness_label": (
                    f"latest {freshness.get('latest_available_date', '')}, "
                    f"expected {freshness.get('expected_date', '')}"
                ).strip(", "),
                "confidence_impact": str(item.get("confidence_impact") or ""),
                "affected_sections": affected_sections,
            }
        )
    must_review_items = []
    for item in (daily_review.get("next_day_plan") or {}).get("must_review_items") or []:
        reasons = []
        actions: list[str] = []
        priorities: list[str] = []
        for reason in item.get("reasons") or []:
            detail = reason.get("reason") if isinstance(reason.get("reason"), dict) else {}
            summary = str(detail.get("setup") or detail.get("summary") or "manual review")
            reasons.append(
                {
                    "strategy_id": str(reason.get("strategy_id") or ""),
                    "summary": summary,
                    "detail": detail,
                }
            )
        for strategy_item in daily_review.get("strategy_items") or []:
            if strategy_item.get("asset_id") != item.get("asset_id"):
                continue
            actions.append(str(strategy_item.get("action") or "manual_review"))
            priorities.append(str(strategy_item.get("review_priority") or "P2"))
        review_priority = sorted(priorities)[0] if priorities else "P2"
        must_review_items.append(
            {
                "asset_id": str(item.get("asset_id") or ""),
                "ts_code": str(item.get("ts_code") or ""),
                "stock_name": str(item.get("stock_name") or ""),
                "strategy_ids": [str(value) for value in item.get("strategy_ids") or []],
                "review_priority": review_priority,
                "actions": actions or ["manual_review"],
                "reasons": reasons,
            }
        )
    state = "partial" if warnings else "ready"
    return {
        "trade_date": trade_date,
        "state": state,
        "selected_run": selected_run,
        "summary": {
            "market_status": str((daily_review.get("market_review") or {}).get("risk_state") or ""),
            "overall_position_bias": str((daily_review.get("operator_plan") or {}).get("overall_position_bias") or ""),
            "lhb_conclusion": str(((daily_review.get("strategy_summaries") or {}).get("lhb") or {}).get("conclusion") or ""),
            "mid_trend_conclusion": str(((daily_review.get("strategy_summaries") or {}).get("mid_trend") or {}).get("conclusion") or ""),
            "technical_bottleneck_conclusion": str(
                (((daily_review.get("strategy_summaries") or {}).get("technical_bottleneck") or {}).get("conclusion") or "")
            ),
            "must_review_asset_ids": [item["asset_id"] for item in must_review_items],
            "warning_count": len(warnings),
        },
        "warnings": warnings,
        "missing_sources": missing_sources,
        "sections": {
            "data_readiness": {
                "status": "partial" if warnings else "success",
                "warnings": warnings,
                "items": data_items,
            },
            "market_review": {
                "status": "partial" if warnings else "success",
                "warnings": [warning for warning in warnings if "lhb_feed" not in warning],
                **(daily_review.get("market_review") or {}),
            },
            "strategy_summaries": {
                "lhb": _strategy_card(daily_review, "lhb", warnings),
                "mid_trend": _strategy_card(daily_review, "mid_trend", warnings),
                "technical_bottleneck": _strategy_card(daily_review, "technical_bottleneck", warnings),
            },
            "holding_review": {
                "status": "success" if daily_review.get("holding_reviews") else "empty",
                "warnings": [],
                "items": daily_review.get("holding_reviews") or [],
            },
            "operator_plan": {
                "status": "success",
                "warnings": [],
                **(daily_review.get("operator_plan") or operator_plan_template),
            },
            "next_day_checklist": {
                "status": "partial" if warnings else "success",
                "warnings": warnings,
                "must_review_items": must_review_items,
                "data_warnings": list(manifest.get("warnings") or warnings),
            },
        },
        "artifacts": _build_artifacts(trade_date, selected_run["run_id"], report_paths),
    }


def _strategy_card(daily_review: dict[str, Any], strategy_id: str, warnings: list[str]) -> dict[str, Any]:
    summary = ((daily_review.get("strategy_summaries") or {}).get(strategy_id) or {}).copy()
    top_items = []
    for item in daily_review.get("strategy_items") or []:
        if item.get("strategy_id") != strategy_id:
            continue
        reason = item.get("reason") if isinstance(item.get("reason"), dict) else {}
        top_items.append(
            {
                "asset_id": str(item.get("asset_id") or ""),
                "stock_name": str(item.get("stock_name") or ""),
                "action": str(item.get("action") or ""),
                "review_priority": str(item.get("review_priority") or "P2"),
                "reason_summary": str(reason.get("setup") or reason.get("summary") or "manual review"),
            }
        )
    summary["warnings"] = warnings if strategy_id == "lhb" else []
    summary["top_items"] = top_items[:3]
    return summary


def _affected_sections_for(source_key: str, item: dict[str, Any]) -> list[str]:
    if source_key == "lhb_feed":
        return ["data_readiness", "strategy_summaries.lhb", "next_day_checklist"]
    modules = [str(value) for value in item.get("blocking_modules") or []]
    return ["data_readiness", *modules]


def _media_type_for(kind: str) -> str:
    return {
        "json": "application/json",
        "manifest": "application/json",
        "operator_plan": "application/json",
        "markdown": "text/markdown; charset=utf-8",
        "evidence": "application/json",
    }.get(kind, "application/octet-stream")
```

- [ ] **Step 4: Run the backend unit tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_daily_review_lite.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard_daily_review_lite.py src/stock_research/dashboard/daily_review_lite.py
git commit -m "feat: add daily review lite backend mapper"
```

---

### Task 2: Expose Lite API and Controlled Artifact Routes

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write the failing route tests**

Add to `tests/test_dashboard_app.py`:

```python
def test_daily_review_lite_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_daily_review_lite",
        lambda trade_date: {
            "trade_date": trade_date,
            "state": "ready",
            "selected_run": {
                "run_id": "daily_review_v1:2026-06-20:abc123",
                "report_type": "daily_review_v1",
                "status": "success",
                "updated_at": "2026-06-20T22:05:00+08:00",
                "source": "report_run",
                "artifact_health": "healthy",
            },
            "summary": None,
            "warnings": [],
            "missing_sources": [],
            "sections": {},
            "artifacts": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/daily-review-lite?trade_date=2026-06-20")

    assert response.status_code == 200
    assert response.json()["state"] == "ready"


def test_daily_review_lite_route_rejects_invalid_trade_date():
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/daily-review-lite?trade_date=20260620")

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid trade_date"


def test_daily_review_lite_artifact_route_streams_registered_file(monkeypatch, tmp_path):
    artifact = tmp_path / "daily_review.md"
    artifact.write_text("# Daily Review", encoding="utf-8")
    monkeypatch.setattr(
        dashboard_app,
        "resolve_daily_review_lite_artifact",
        lambda trade_date, key, run_id=None: {
            "path": str(artifact),
            "filename": artifact.name,
            "media_type": "text/markdown; charset=utf-8",
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=daily_review_markdown&run_id=daily_review_v1:2026-06-20:abc123"
    )

    assert response.status_code == 200
    assert response.text == "# Daily Review"


def test_daily_review_lite_artifact_route_returns_404_for_unknown_key(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "resolve_daily_review_lite_artifact",
        lambda trade_date, key, run_id=None: None,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=bad")

    assert response.status_code == 404
    assert response.json()["detail"] == "artifact not found"
```

- [ ] **Step 2: Run the route tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_app.py -q
```

Expected: FAIL because the new routes are not registered.

- [ ] **Step 3: Implement the FastAPI routes**

Modify `src/stock_research/dashboard/app.py`:

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from stock_research.dashboard.daily_review_lite import (
    load_daily_review_lite,
    resolve_daily_review_lite_artifact,
)
```

Add the validation helper near the top of the file:

```python
def _validate_trade_date(trade_date: str) -> str:
    from datetime import date

    try:
        date.fromisoformat(trade_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid trade_date")
    return trade_date
```

Add these routes inside `create_app()`:

```python
    @app.get("/api/daily-review-lite")
    def daily_review_lite(trade_date: str):
        validated = _validate_trade_date(trade_date)
        return load_daily_review_lite(validated)

    @app.get("/api/daily-review-lite/artifacts")
    def daily_review_lite_artifact(
        trade_date: str,
        key: str,
        run_id: str | None = None,
    ):
        validated = _validate_trade_date(trade_date)
        artifact = resolve_daily_review_lite_artifact(validated, key=key, run_id=run_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(
            artifact["path"],
            filename=artifact["filename"],
            media_type=artifact["media_type"],
        )
```

- [ ] **Step 4: Run the route tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_app.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/app.py tests/test_dashboard_app.py
git commit -m "feat: add daily review lite api routes"
```

---

### Task 3: Add the Frontend Lite Types and API Client

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write the failing frontend client test**

Add to `dashboard/tests/client.test.ts`:

```ts
import { fetchDailyReviewLite } from '../src/api/client';

it('fetches daily review lite for a trade date', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      trade_date: '2026-06-20',
      state: 'ready',
      selected_run: null,
      summary: null,
      warnings: [],
      missing_sources: [],
      sections: {},
      artifacts: []
    })
  });
  vi.stubGlobal('fetch', fetchMock);

  const result = await fetchDailyReviewLite('2026-06-20');

  expect(fetchMock).toHaveBeenCalledWith('/api/daily-review-lite?trade_date=2026-06-20');
  expect(result.state).toBe('ready');
});
```

- [ ] **Step 2: Run the client tests to verify failure**

Run:

```bash
pnpm --dir dashboard exec vitest run tests/client.test.ts
```

Expected: FAIL because `fetchDailyReviewLite` and the supporting types do not exist.

- [ ] **Step 3: Implement the Lite API types and client**

Append these types to `dashboard/src/api/types.ts`:

```ts
export type DailyReviewLiteState = 'ready' | 'partial' | 'empty' | 'failed';

export type DailyReviewLiteArtifact = {
  key: string;
  label: string;
  kind: 'json' | 'markdown' | 'manifest' | 'operator_plan' | 'evidence' | string;
  url: string;
};

export type DailyReviewLiteReason = {
  strategy_id: string;
  summary: string;
  detail?: {
    setup?: string;
    summary?: string;
    [key: string]: unknown;
  };
};

export type DailyReviewLiteTopItem = {
  asset_id: string;
  stock_name: string;
  action: string;
  review_priority: string;
  reason_summary: string;
};

export type DailyReviewLiteStrategyCard = {
  conclusion: string;
  warnings: string[];
  top_items: DailyReviewLiteTopItem[];
  short_allowed?: boolean;
  watch_count?: number;
  forbidden_actions?: string[];
  portfolio_health?: string;
  holding_count?: number;
  upgraded_count?: number;
  research_required_count?: number;
};

export type DailyReviewLiteResponse = {
  trade_date: string;
  state: DailyReviewLiteState;
  selected_run: {
    run_id: string;
    report_type: 'daily_review_v1';
    status: 'success' | 'partial' | 'failed';
    updated_at?: string;
    source: 'report_run' | 'fallback';
    artifact_health: 'healthy' | 'missing' | 'invalid';
    artifact_health_detail: Record<string, 'healthy' | 'missing' | 'invalid'>;
  } | null;
  summary: {
    market_status: string;
    overall_position_bias: string;
    lhb_conclusion: string;
    mid_trend_conclusion: string;
    technical_bottleneck_conclusion: string;
    must_review_asset_ids: string[];
    warning_count: number;
  } | null;
  warnings: string[];
  missing_sources: Array<{
    source_key: string;
    summary: string;
    affected_sections: string[];
    confidence_impact: string;
  }>;
  sections: {
    data_readiness: {
      status: 'success' | 'partial' | 'empty';
      warnings: string[];
      items: Array<{
        source_key: string;
        status: string;
        summary: string;
        freshness_label: string;
        confidence_impact: string;
        affected_sections: string[];
      }>;
    };
    market_review: {
      status: 'success' | 'partial' | 'empty';
      warnings: string[];
      emotion_state: string;
      risk_state: string;
      trend_environment: string;
      style_bias: string;
      target_exposure: string;
      market_comment: string;
    } | null;
    strategy_summaries: {
      lhb: DailyReviewLiteStrategyCard | null;
      mid_trend: DailyReviewLiteStrategyCard | null;
      technical_bottleneck: DailyReviewLiteStrategyCard | null;
    };
    holding_review: {
      status: 'success' | 'partial' | 'empty';
      warnings: string[];
      items: Array<{
        strategy_id: string;
        asset_id: string;
        current_state: string;
        action: string;
        risk_status?: string;
        exit_condition?: string;
      }>;
    };
    operator_plan: {
      status: 'success' | 'partial' | 'empty';
      warnings: string[];
      mode: string;
      overall_position_bias: string;
      must_check_before_open: string[];
      forbidden_actions: string[];
    } | null;
    next_day_checklist: {
      status: 'success' | 'partial' | 'empty';
      warnings: string[];
      must_review_items: Array<{
        asset_id: string;
        ts_code: string;
        stock_name: string;
        strategy_ids: string[];
        review_priority: string;
        actions: string[];
        reasons: DailyReviewLiteReason[];
      }>;
      data_warnings: string[];
    };
  };
  artifacts: DailyReviewLiteArtifact[];
};
```

Modify the import list in `dashboard/src/api/client.ts`:

```ts
  DailyReviewLiteResponse,
```

Add this function above `getJson`:

```ts
export async function fetchDailyReviewLite(tradeDate: string): Promise<DailyReviewLiteResponse> {
  return getJson(`/api/daily-review-lite?trade_date=${encodeURIComponent(tradeDate)}`);
}
```

- [ ] **Step 4: Run the client tests**

Run:

```bash
pnpm --dir dashboard exec vitest run tests/client.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add daily review lite frontend api client"
```

---

### Task 4: Build the Daily Review Lite Page and Fixed Strategy Cards

**Files:**
- Create: `dashboard/src/pages/DailyReviewLitePage.tsx`
- Create: `dashboard/src/components/DailyReviewLiteStrategyCards.tsx`
- Create: `dashboard/src/components/DailyReviewLiteArtifactLinks.tsx`
- Modify: `dashboard/src/styles.css`
- Create: `dashboard/tests/daily-review-lite-page.test.tsx`

- [ ] **Step 1: Write the failing page tests**

Create `dashboard/tests/daily-review-lite-page.test.tsx`:

```tsx
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DailyReviewLitePage } from '../src/pages/DailyReviewLitePage';

const apiMocks = vi.hoisted(() => ({
  fetchDailyReviewLite: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makePayload(overrides: Record<string, unknown> = {}) {
  return {
    trade_date: '2026-06-20',
    state: 'ready',
    selected_run: {
      run_id: 'daily_review_v1:2026-06-20:abc123',
      report_type: 'daily_review_v1',
      status: 'partial',
      updated_at: '2026-06-20T22:05:00+08:00',
      source: 'report_run',
      artifact_health: 'healthy',
      artifact_health_detail: {
        daily_review_json: 'healthy',
        manifest_json: 'healthy',
        operator_plan_template_json: 'healthy'
      }
    },
    summary: {
      market_status: 'defensive',
      overall_position_bias: 'defensive',
      lhb_conclusion: 'trial',
      mid_trend_conclusion: 'hold core names',
      technical_bottleneck_conclusion: 'monitor upgrades only',
      must_review_asset_ids: ['CN:SH:600000'],
      warning_count: 1
    },
    warnings: ['source_missing:lhb_feed'],
    missing_sources: [
      {
        source_key: 'lhb_feed',
        summary: 'lhb payload missing for trade date',
        affected_sections: ['strategy_summaries.lhb', 'next_day_checklist'],
        confidence_impact: 'LHB conclusion confidence reduced'
      }
    ],
    sections: {
      data_readiness: {
        status: 'partial',
        warnings: ['source_missing:lhb_feed'],
        items: []
      },
      market_review: {
        status: 'success',
        warnings: [],
        emotion_state: 'cold',
        risk_state: 'defensive',
        trend_environment: 'retreat',
        style_bias: 'large_cap_defensive',
        target_exposure: 'defensive',
        market_comment: 'Stay defensive.'
      },
      strategy_summaries: {
        lhb: {
          conclusion: 'trial',
          short_allowed: true,
          watch_count: 1,
          forbidden_actions: ['chase stale LHB names'],
          warnings: ['source_missing:lhb_feed'],
          top_items: [
            {
              asset_id: 'CN:SH:600000',
              stock_name: '浦发银行',
              action: 'manual_review',
              review_priority: 'P0',
              reason_summary: 'bank rotation leader'
            }
          ]
        },
        mid_trend: {
          conclusion: 'hold core names',
          portfolio_health: 'stable',
          holding_count: 1,
          warnings: [],
          top_items: []
        },
        technical_bottleneck: {
          conclusion: 'monitor upgrades only',
          upgraded_count: 1,
          research_required_count: 0,
          warnings: [],
          top_items: []
        }
      },
      holding_review: {
        status: 'success',
        warnings: [],
        items: [
          {
            strategy_id: 'lhb',
            asset_id: 'CN:SH:600000',
            current_state: 'watch',
            action: 'manual_review'
          }
        ]
      },
      operator_plan: {
        status: 'success',
        warnings: [],
        mode: 'manual_review_only',
        overall_position_bias: 'defensive',
        must_check_before_open: ['CN:SH:600000'],
        forbidden_actions: ['chase stale LHB names']
      },
      next_day_checklist: {
        status: 'partial',
        warnings: ['source_missing:lhb_feed'],
        must_review_items: [
          {
            asset_id: 'CN:SH:600000',
            ts_code: '600000.SH',
            stock_name: '浦发银行',
            strategy_ids: ['lhb'],
            review_priority: 'P0',
            actions: ['manual_review'],
            reasons: [
              {
                strategy_id: 'lhb',
                summary: 'bank rotation leader',
                detail: { setup: 'bank rotation leader' }
              }
            ]
          }
        ],
        data_warnings: ['source_missing:lhb_feed']
      }
    },
    artifacts: [
      {
        key: 'daily_review_json',
        label: 'Daily Review JSON',
        kind: 'json',
        url: '/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=daily_review_json'
      }
    ],
    ...overrides
  };
}

describe('DailyReviewLitePage', () => {
  it('renders fixed strategy cards and artifact links', async () => {
    apiMocks.fetchDailyReviewLite.mockResolvedValue(makePayload());

    render(<DailyReviewLitePage />);

    expect(await screen.findByText('Daily Review Lite')).toBeInTheDocument();
    expect(screen.getByText('LHB')).toBeInTheDocument();
    expect(screen.getByText('Mid Trend')).toBeInTheDocument();
    expect(screen.getByText('Technical Bottleneck')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Daily Review JSON' })).toHaveAttribute(
      'href',
      '/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=daily_review_json'
    );
  });

  it('renders an empty state when no report exists', async () => {
    apiMocks.fetchDailyReviewLite.mockResolvedValue(makePayload({ state: 'empty', selected_run: null, summary: null }));

    render(<DailyReviewLitePage />);

    expect(await screen.findByText('No report found for selected date')).toBeInTheDocument();
  });

  it('renders partial warnings in the page and section', async () => {
    apiMocks.fetchDailyReviewLite.mockResolvedValue(makePayload({ state: 'partial' }));

    render(<DailyReviewLitePage />);

    expect(await screen.findAllByText('source_missing:lhb_feed')).toHaveLength(3);
  });

  it('renders failed state with artifact health', async () => {
    apiMocks.fetchDailyReviewLite.mockResolvedValue(
      makePayload({
        state: 'failed',
        selected_run: {
          run_id: 'daily_review_v1:2026-06-20:abc123',
          report_type: 'daily_review_v1',
          status: 'failed',
          updated_at: '2026-06-20T22:05:00+08:00',
          source: 'report_run',
          artifact_health: 'invalid',
          artifact_health_detail: {
            daily_review_json: 'invalid'
          }
        },
        summary: null
      })
    );

    render(<DailyReviewLitePage />);

    expect(await screen.findByText('Report artifacts could not be read')).toBeInTheDocument();
    expect(screen.getByText('Artifact health: invalid')).toBeInTheDocument();
  });

  it('renders the fallback banner when loaded from package scan', async () => {
    apiMocks.fetchDailyReviewLite.mockResolvedValue(
      makePayload({
        selected_run: {
          run_id: 'fallback:2026-06-20',
          report_type: 'daily_review_v1',
          status: 'partial',
          updated_at: '',
          source: 'fallback',
          artifact_health: 'healthy',
          artifact_health_detail: {
            daily_review_json: 'healthy'
          }
        }
      })
    );

    render(<DailyReviewLitePage />);

    expect(await screen.findByText('Loaded from fallback package scan')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the page tests to verify failure**

Run:

```bash
pnpm --dir dashboard exec vitest run tests/daily-review-lite-page.test.tsx
```

Expected: FAIL because the page and supporting components do not exist.

- [ ] **Step 3: Implement the page, fixed strategy cards, artifact links, and styles**

Create `dashboard/src/components/DailyReviewLiteStrategyCards.tsx`:

```tsx
type StrategyCard = {
  conclusion: string;
  warnings: string[];
  top_items: Array<{
    asset_id: string;
    stock_name: string;
    action: string;
    review_priority: string;
    reason_summary: string;
  }>;
  [key: string]: unknown;
};

type DailyReviewLiteStrategyCardsProps = {
  strategies: {
    lhb: StrategyCard | null;
    mid_trend: StrategyCard | null;
    technical_bottleneck: StrategyCard | null;
  };
};

function StrategyCardSection({ title, card }: { title: string; card: StrategyCard | null }) {
  if (!card) {
    return (
      <article className="daily-review-strategy-card">
        <h3>{title}</h3>
        <p className="muted">No data.</p>
      </article>
    );
  }
  return (
    <article className="daily-review-strategy-card">
      <h3>{title}</h3>
      <p>{card.conclusion}</p>
      {card.warnings.length > 0 ? <p className="warning-pill">{card.warnings.join(', ')}</p> : null}
      <ul>
        {card.top_items.map((item) => (
          <li key={`${title}-${item.asset_id}`}>
            {item.asset_id} / {item.stock_name} / {item.action} / {item.review_priority} / {item.reason_summary}
          </li>
        ))}
      </ul>
    </article>
  );
}

export function DailyReviewLiteStrategyCards({ strategies }: DailyReviewLiteStrategyCardsProps) {
  return (
    <div className="daily-review-strategy-grid">
      <StrategyCardSection title="LHB" card={strategies.lhb} />
      <StrategyCardSection title="Mid Trend" card={strategies.mid_trend} />
      <StrategyCardSection title="Technical Bottleneck" card={strategies.technical_bottleneck} />
    </div>
  );
}
```

Create `dashboard/src/components/DailyReviewLiteArtifactLinks.tsx`:

```tsx
import type { DailyReviewLiteArtifact } from '../api/types';

type DailyReviewLiteArtifactLinksProps = {
  artifacts: DailyReviewLiteArtifact[];
};

export function DailyReviewLiteArtifactLinks({ artifacts }: DailyReviewLiteArtifactLinksProps) {
  if (artifacts.length === 0) {
    return <p className="muted">No registered artifacts.</p>;
  }
  return (
    <div className="daily-review-artifact-list">
      {artifacts.map((artifact) => (
        <a key={artifact.key} href={artifact.url}>
          {artifact.label}
        </a>
      ))}
    </div>
  );
}
```

Create `dashboard/src/pages/DailyReviewLitePage.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { fetchDailyReviewLite } from '../api/client';
import type { DailyReviewLiteResponse } from '../api/types';
import { DailyReviewLiteArtifactLinks } from '../components/DailyReviewLiteArtifactLinks';
import { DailyReviewLiteStrategyCards } from '../components/DailyReviewLiteStrategyCards';

const DEFAULT_TRADE_DATE = '2026-06-20';

export function DailyReviewLitePage() {
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [payload, setPayload] = useState<DailyReviewLiteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    setError(null);
    fetchDailyReviewLite(tradeDate)
      .then((result) => {
        if (!ignore) setPayload(result);
      })
      .catch((err: unknown) => {
        if (!ignore) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      ignore = true;
    };
  }, [tradeDate]);

  return (
    <main className="daily-review-page">
      <header className="daily-review-header">
        <div>
          <h1>Daily Review Lite</h1>
          <p>Structured read-only review of the Daily Review v1 report package</p>
        </div>
        <label>
          Trade date
          <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
        </label>
      </header>
      {error ? <p className="warning-banner">{error}</p> : null}
      {!payload ? (
        <p className="muted">Loading daily review...</p>
      ) : payload.state === 'empty' ? (
        <section className="daily-review-state-card">
          <p>No report found for selected date</p>
        </section>
      ) : (
        <>
          <section className="daily-review-state-card">
            <p>
              {payload.selected_run?.source === 'fallback'
                ? 'Loaded from fallback package scan'
                : 'Loaded from report.run'}
            </p>
            <p>Artifact health: {payload.selected_run?.artifact_health ?? 'unknown'}</p>
            {payload.state === 'failed' ? <p className="warning-banner">Report artifacts could not be read</p> : null}
            {payload.warnings.length > 0 ? <p className="warning-banner">{payload.warnings.join(', ')}</p> : null}
          </section>

          <section className="daily-review-section">
            <h2>Data Readiness</h2>
            <p>{payload.sections.data_readiness.status}</p>
            {payload.sections.data_readiness.warnings.map((warning: string) => (
              <p key={warning} className="warning-pill">
                {warning}
              </p>
            ))}
          </section>

          <section className="daily-review-section">
            <h2>Market Review</h2>
            <p>{payload.sections.market_review?.market_comment ?? 'No market review.'}</p>
          </section>

          <section className="daily-review-section">
            <h2>Strategy Summaries</h2>
            <DailyReviewLiteStrategyCards strategies={payload.sections.strategy_summaries} />
          </section>

          <section className="daily-review-section">
            <h2>Holding Review</h2>
            <ul>
              {payload.sections.holding_review.items.map((item) => (
                <li key={`${item.strategy_id}-${item.asset_id}`}>
                  {item.strategy_id} / {item.asset_id} / {item.action}
                </li>
              ))}
            </ul>
          </section>

          <section className="daily-review-section">
            <h2>Operator Plan</h2>
            <p>{payload.sections.operator_plan?.mode ?? 'No operator plan.'}</p>
          </section>

          <section className="daily-review-section">
            <h2>Next-day Checklist</h2>
            {payload.sections.next_day_checklist.warnings.map((warning: string) => (
              <p key={warning} className="warning-pill">
                {warning}
              </p>
            ))}
            <ul>
              {payload.sections.next_day_checklist.must_review_items.map((item) => (
                <li key={item.asset_id}>
                  {item.asset_id} / {item.review_priority} / {item.reasons.map((reason) => reason.summary).join(', ')}
                </li>
              ))}
            </ul>
          </section>

          <section className="daily-review-section">
            <h2>Artifacts</h2>
            <DailyReviewLiteArtifactLinks artifacts={payload.artifacts} />
          </section>
        </>
      )}
    </main>
  );
}
```

Append to `dashboard/src/styles.css`:

```css
.daily-review-page {
  max-width: 1120px;
  margin: 0 auto;
  padding: 24px;
  display: grid;
  gap: 20px;
}

.daily-review-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
}

.daily-review-state-card,
.daily-review-section,
.daily-review-strategy-card {
  border: 1px solid #d6d0c4;
  border-radius: 16px;
  padding: 16px;
  background: linear-gradient(180deg, #fffaf3 0%, #f4efe6 100%);
}

.daily-review-strategy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.daily-review-artifact-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.warning-banner,
.warning-pill {
  color: #8b3d1f;
}
```

- [ ] **Step 4: Run the page tests**

Run:

```bash
pnpm --dir dashboard exec vitest run tests/daily-review-lite-page.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/pages/DailyReviewLitePage.tsx dashboard/src/components/DailyReviewLiteStrategyCards.tsx dashboard/src/components/DailyReviewLiteArtifactLinks.tsx dashboard/src/styles.css dashboard/tests/daily-review-lite-page.test.tsx
git commit -m "feat: add daily review lite page"
```

---

### Task 5: Add the Root Shell Route Split and Verify the Frontend Build

**Files:**
- Create: `dashboard/src/RootApp.tsx`
- Modify: `dashboard/src/main.tsx`
- Create: `dashboard/tests/root-app.test.tsx`

- [ ] **Step 1: Write the failing root-shell tests**

Create `dashboard/tests/root-app.test.tsx`:

```tsx
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RootApp } from '../src/RootApp';

vi.mock('../src/App', () => ({
  App: () => <div>Workbench App</div>
}));

vi.mock('../src/pages/DailyReviewLitePage', () => ({
  DailyReviewLitePage: () => <div>Daily Review Lite Page</div>
}));

afterEach(() => {
  window.history.pushState({}, '', '/');
});

describe('RootApp', () => {
  it('renders the lite page for /daily-review-lite', () => {
    window.history.pushState({}, '', '/daily-review-lite');

    render(<RootApp />);

    expect(screen.getByText('Daily Review Lite Page')).toBeInTheDocument();
  });

  it('renders the existing workbench app for /', () => {
    window.history.pushState({}, '', '/');

    render(<RootApp />);

    expect(screen.getByText('Workbench App')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the root-shell tests to verify failure**

Run:

```bash
pnpm --dir dashboard exec vitest run tests/root-app.test.tsx
```

Expected: FAIL because `RootApp` does not exist and `main.tsx` still renders `App`.

- [ ] **Step 3: Implement the lightweight route shell**

Create `dashboard/src/RootApp.tsx`:

```tsx
import { App } from './App';
import { DailyReviewLitePage } from './pages/DailyReviewLitePage';

export function RootApp() {
  return window.location.pathname.startsWith('/daily-review-lite') ? (
    <DailyReviewLitePage />
  ) : (
    <App />
  );
}
```

Modify `dashboard/src/main.tsx`:

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { RootApp } from './RootApp';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <RootApp />
  </React.StrictMode>
);
```

- [ ] **Step 4: Run the route-shell tests and the frontend build**

Run:

```bash
pnpm --dir dashboard exec vitest run tests/root-app.test.tsx
pnpm --dir dashboard build
```

Expected:

- `tests/root-app.test.tsx`: PASS
- `pnpm --dir dashboard build`: build completes successfully

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/RootApp.tsx dashboard/src/main.tsx dashboard/tests/root-app.test.tsx
git commit -m "feat: route dashboard to daily review lite page"
```

---

## Final Verification

Run the full targeted verification set:

```bash
.venv/bin/pytest tests/test_dashboard_daily_review_lite.py tests/test_dashboard_app.py -q
pnpm --dir dashboard exec vitest run tests/client.test.ts tests/daily-review-lite-page.test.tsx tests/root-app.test.tsx
pnpm --dir dashboard build
```

Expected:

- backend tests PASS
- frontend unit tests PASS
- frontend production build succeeds

## Spec Coverage Check

- `report.report_run` priority and fallback-only compatibility: Task 1
- `ready / partial / empty / failed` mapper semantics: Task 1
- controlled artifact URLs with `trade_date`, `key`, and `run_id`: Tasks 1 and 2
- `400` invalid `trade_date`, `200` for business states, `404` unknown artifact key: Task 2
- frontend dedicated Lite view model and no raw paths: Tasks 3 and 4
- fixed `LHB / Mid Trend / Technical Bottleneck` strategy summaries: Task 4
- no writeback / no execution / no pipeline mutation: enforced by all tasks, especially Task 1 and Task 4
