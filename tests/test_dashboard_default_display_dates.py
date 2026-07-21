from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import (
    daily_review_lite,
    display_date_gate,
    evidence_digest,
    market_monitor,
    review_queue,
    search,
)


def _manifest_modules(trade_date: str, *, run_id: str, browser_status: str | None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module in (
        "daily_bars",
        "technical_features",
        "score_topn",
        "lhb_features",
        "tech_bottleneck_candidates",
        "review_queue_strategy_manifest",
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
    ):
        metadata: dict[str, object] = {}
        if module == "strategy_tech_bottleneck":
            metadata = {"candidate_snapshot_latest_date": trade_date}
        rows.append(
            {
                "run_id": run_id,
                "trade_date": trade_date,
                "latest_trade_date": trade_date,
                "module": module,
                "status": "success",
                "metadata": metadata,
            }
        )
    if browser_status is not None:
        rows.append(
            {
                "run_id": run_id,
                "trade_date": trade_date,
                "latest_trade_date": trade_date,
                "module": "dashboard_browser_acceptance",
                "status": browser_status,
                "metadata": {},
            }
        )
    return rows


def _install_gate_modules(monkeypatch, modules: list[dict[str, object]]) -> None:
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from="2026-07-21"),
    )
    monkeypatch.setattr(display_date_gate, "load_strategy_contracts", lambda profile="balanced": {})
    monkeypatch.setattr(display_date_gate, "load_recent_data_run_manifest", lambda **_kwargs: modules)
    real_select = display_date_gate.select_display_date
    monkeypatch.setattr(
        display_date_gate,
        "select_display_date",
        lambda rows, *, latest_market_date: real_select(
            rows,
            latest_market_date=latest_market_date,
            now=datetime(2026, 7, 21, 21, 0, tzinfo=display_date_gate.LOCAL_ZONE),
        ),
    )


def _install_boundary_gate(monkeypatch, browser_status: str | None) -> None:
    _install_gate_modules(
        monkeypatch,
        [
            *_manifest_modules("2026-07-20", run_id="prior", browser_status=None),
            *_manifest_modules("2026-07-21", run_id="candidate", browser_status=browser_status),
        ],
    )


@pytest.mark.parametrize(
    ("include_prior", "candidate_status", "expected_trade_date"),
    [
        (True, None, "2026-07-20"),
        (False, None, ""),
        (True, "failed", "2026-07-20"),
        (True, "success", "2026-07-21"),
    ],
)
def test_select_display_date_never_selects_ready_future_manifest(
    monkeypatch,
    include_prior,
    candidate_status,
    expected_trade_date,
):
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from="2026-07-21"),
    )
    monkeypatch.setattr(display_date_gate, "load_strategy_contracts", lambda profile="balanced": {})
    modules = [
        *(
            _manifest_modules("2026-07-20", run_id="prior", browser_status=None)
            if include_prior
            else []
        ),
        *_manifest_modules("2026-07-21", run_id="candidate", browser_status=candidate_status),
        *_manifest_modules("2026-07-22", run_id="future", browser_status="success"),
    ]

    gate = display_date_gate.select_display_date(
        modules,
        latest_market_date="2026-07-21",
        now=datetime(2026, 7, 21, 21, 0, tzinfo=display_date_gate.LOCAL_ZONE),
    )

    assert gate["display_trade_date"] == expected_trade_date


@pytest.mark.parametrize(
    ("include_prior", "candidate_status", "expected_trade_date", "expected_status"),
    [
        (True, None, "2026-07-20", "ready"),
        (False, None, "", "blocked"),
        (True, "failed", "2026-07-20", "ready"),
        (True, "success", "2026-07-21", "ready"),
    ],
)
def test_default_trade_date_resolver_never_selects_ready_future_manifest(
    monkeypatch,
    include_prior,
    candidate_status,
    expected_trade_date,
    expected_status,
):
    modules = [
        *(
            _manifest_modules("2026-07-20", run_id="prior", browser_status=None)
            if include_prior
            else []
        ),
        *_manifest_modules("2026-07-21", run_id="candidate", browser_status=candidate_status),
        *_manifest_modules("2026-07-22", run_id="future", browser_status="success"),
    ]
    _install_gate_modules(monkeypatch, modules)

    result = display_date_gate.resolve_default_trade_date({"latest_market_date": "2026-07-21"})

    assert result["trade_date"] == expected_trade_date
    assert result["status"] == expected_status


def test_review_market_and_daily_defaults_ignore_ready_future_manifest(monkeypatch):
    modules = [
        *_manifest_modules("2026-07-20", run_id="prior", browser_status=None),
        *_manifest_modules("2026-07-21", run_id="candidate", browser_status="failed"),
        *_manifest_modules("2026-07-22", run_id="future", browser_status="success"),
    ]
    _install_gate_modules(monkeypatch, modules)
    summary = {"latest_market_date": "2026-07-21", "latest_score_date": "2026-07-21"}

    assert review_queue._default_display_trade_date(summary) == "2026-07-20"
    assert market_monitor._default_display_trade_date(summary) == "2026-07-20"

    monkeypatch.setattr(daily_review_lite, "load_platform_summary", lambda service: summary)
    selected_dates: list[str] = []

    def latest_run(trade_date, *, service):
        selected_dates.append(trade_date)
        return {"run_id": "registered"}

    monkeypatch.setattr(daily_review_lite, "_latest_registered_run", latest_run)
    monkeypatch.setattr(
        daily_review_lite,
        "_load_payload_from_run",
        lambda run, *, selected_trade_date: {"trade_date": selected_trade_date},
    )

    payload = daily_review_lite.build_daily_review_lite(service="test")

    assert payload["trade_date"] == "2026-07-20"
    assert selected_dates == ["2026-07-20"]


@pytest.mark.parametrize(
    ("browser_status", "expected_trade_date"),
    [(None, "2026-07-20"), ("failed", "2026-07-20"), ("success", "2026-07-21"), ("degraded", "2026-07-21")],
)
def test_default_trade_date_resolver_applies_browser_acceptance_gate(
    monkeypatch,
    browser_status,
    expected_trade_date,
):
    _install_boundary_gate(monkeypatch, browser_status)

    result = display_date_gate.resolve_default_trade_date({"latest_market_date": "2026-07-21"})

    assert result["trade_date"] == expected_trade_date
    assert result["status"] == "ready"


@pytest.mark.parametrize(
    ("browser_status", "expected_trade_date"),
    [(None, "2026-07-20"), ("failed", "2026-07-20"), ("success", "2026-07-21"), ("degraded", "2026-07-21")],
)
def test_daily_review_default_uses_shared_display_gate(
    monkeypatch,
    browser_status,
    expected_trade_date,
):
    _install_boundary_gate(monkeypatch, browser_status)
    monkeypatch.setattr(
        daily_review_lite,
        "load_platform_summary",
        lambda service: {"latest_market_date": "2026-07-21"},
    )
    selected_dates: list[str] = []

    def latest_run(trade_date, *, service):
        selected_dates.append(trade_date)
        return {"run_id": "registered"}

    monkeypatch.setattr(daily_review_lite, "_latest_registered_run", latest_run)
    monkeypatch.setattr(
        daily_review_lite,
        "_load_payload_from_run",
        lambda run, *, selected_trade_date: {"trade_date": selected_trade_date},
    )
    monkeypatch.setattr(
        daily_review_lite,
        "_generate_and_register_run",
        lambda *_args, **_kwargs: pytest.fail("registered gated run must be selected without generation"),
    )

    payload = daily_review_lite.build_daily_review_lite(service="test")

    assert payload["trade_date"] == expected_trade_date
    assert selected_dates == [expected_trade_date]


@pytest.mark.parametrize(
    ("browser_status", "expected_trade_date"),
    [(None, "2026-07-20"), ("failed", "2026-07-20"), ("success", "2026-07-21"), ("degraded", "2026-07-21")],
)
def test_evidence_digest_default_uses_shared_display_gate(
    monkeypatch,
    browser_status,
    expected_trade_date,
):
    _install_boundary_gate(monkeypatch, browser_status)
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda score_version, top_n: {"latest_market_date": "2026-07-21"},
    )
    warnings: list[str] = []

    selected = evidence_digest._selected_trade_date(None, "manual_v1", warnings)

    assert selected == expected_trade_date
    assert warnings == []


@pytest.mark.parametrize(
    ("browser_status", "expected_trade_date"),
    [(None, "2026-07-20"), ("failed", "2026-07-20"), ("success", "2026-07-21"), ("degraded", "2026-07-21")],
)
def test_generated_report_search_default_uses_shared_display_gate(
    monkeypatch,
    browser_status,
    expected_trade_date,
):
    _install_boundary_gate(monkeypatch, browser_status)
    monkeypatch.setattr(search, "load_platform_summary", lambda: {"latest_market_date": "2026-07-21"})
    selected_dates: list[str] = []

    def report_links(trade_date):
        selected_dates.append(trade_date)
        return []

    monkeypatch.setattr(search, "load_report_links", report_links)

    assert search._generated_report_results("daily", 5) == []
    assert selected_dates == [expected_trade_date]


@pytest.mark.parametrize("manifest_mode", ["empty", "error"])
def test_daily_review_blocked_default_never_reads_or_records_runs(monkeypatch, manifest_mode):
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from="2026-07-21"),
    )
    monkeypatch.setattr(
        daily_review_lite,
        "load_platform_summary",
        lambda service: {"latest_market_date": "2026-07-21"},
    )

    def manifest_loader(**_kwargs):
        if manifest_mode == "error":
            raise RuntimeError("database unavailable secret=do-not-leak")
        return []

    monkeypatch.setattr(display_date_gate, "load_recent_data_run_manifest", manifest_loader)
    monkeypatch.setattr(
        daily_review_lite,
        "_latest_registered_run",
        lambda *_args, **_kwargs: pytest.fail("blocked default must not read report runs"),
    )
    monkeypatch.setattr(
        daily_review_lite,
        "_generate_and_register_run",
        lambda *_args, **_kwargs: pytest.fail("blocked default must not generate or record artifacts"),
    )

    payload = daily_review_lite.build_daily_review_lite(service="test")

    assert payload["trade_date"] == ""
    assert payload["status"] == "unavailable"
    assert payload["run"]["run_id"] == ""
    assert payload["artifacts"] == []
    assert "do-not-leak" not in str(payload)


@pytest.mark.parametrize("manifest_mode", ["empty", "error"])
def test_evidence_digest_blocked_default_returns_without_candidate_reads(monkeypatch, manifest_mode):
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from="2026-07-21"),
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda score_version, top_n: {"latest_market_date": "2026-07-21"},
    )

    def manifest_loader(**_kwargs):
        if manifest_mode == "error":
            raise RuntimeError("database unavailable secret=do-not-leak")
        return []

    monkeypatch.setattr(display_date_gate, "load_recent_data_run_manifest", manifest_loader)
    monkeypatch.setattr(
        evidence_digest,
        "build_asset_profile",
        lambda **_kwargs: pytest.fail("blocked default must not read candidate evidence"),
    )

    payload = evidence_digest.build_evidence_digest("CN:SH:600519")

    assert payload["trade_date"] == ""
    assert payload["overall_status"] == "BLOCKED"
    assert any("display trade date unavailable" in warning for warning in payload["warnings"])
    assert "do-not-leak" not in str(payload)


@pytest.mark.parametrize("manifest_mode", ["empty", "error"])
def test_global_search_keeps_other_groups_when_generated_reports_are_gate_blocked(monkeypatch, manifest_mode):
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from="2026-07-21"),
    )
    monkeypatch.setattr(search, "load_platform_summary", lambda: {"latest_market_date": "2026-07-21"})

    def manifest_loader(**_kwargs):
        if manifest_mode == "error":
            raise RuntimeError("database unavailable secret=do-not-leak")
        return []

    monkeypatch.setattr(display_date_gate, "load_recent_data_run_manifest", manifest_loader)
    monkeypatch.setattr(search, "_asset_results", lambda *_args: [{"id": "asset:ok"}])
    monkeypatch.setattr(search, "_news_results", lambda *_args: [{"id": "news:ok"}])
    monkeypatch.setattr(search, "_research_report_results", lambda *_args: [{"id": "research:ok"}])
    monkeypatch.setattr(
        search,
        "load_report_links",
        lambda trade_date: pytest.fail(f"blocked generated reports must not read {trade_date}"),
    )

    payload = search.load_global_search("茅台", limit=5)
    groups = {group["key"]: group["items"] for group in payload["groups"]}

    assert groups["assets"] == [{"id": "asset:ok"}]
    assert groups["news"] == [{"id": "news:ok"}]
    assert groups["research_reports"] == [{"id": "research:ok"}]
    assert groups["generated_reports"] == []
    assert any("generated_reports search failed" in warning for warning in payload["warnings"])
    assert "do-not-leak" not in str(payload)


def test_review_queue_blocked_default_returns_empty_without_candidate_reads(monkeypatch):
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from="2026-07-21"),
    )
    monkeypatch.setattr(display_date_gate, "load_recent_data_run_manifest", lambda **_kwargs: [])
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-07-21",
            "latest_score_date": "2026-07-21",
            "topn_preview": [{"asset_id": "CANDIDATE.SZ"}],
        },
    )
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_manifest_snapshot",
        lambda **_kwargs: pytest.fail("blocked default must not read candidate strategy rows"),
    )

    payload = review_queue.build_review_queue()

    assert payload["trade_date"] == ""
    assert all(group["items"] == [] for group in payload["groups"])
    assert any("display trade date unavailable" in warning for warning in payload["warnings"])


def test_market_monitor_blocked_default_returns_empty_without_candidate_reads(monkeypatch):
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from="2026-07-21"),
    )
    monkeypatch.setattr(display_date_gate, "load_recent_data_run_manifest", lambda **_kwargs: [])
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-07-21",
            "latest_factor_date": "2026-07-21",
            "latest_score_date": "2026-07-21",
            "topn_preview": [{"asset_id": "CANDIDATE.SZ"}],
        },
    )
    monkeypatch.setattr(
        market_monitor,
        "load_emotion_stock_lists",
        lambda trade_date: pytest.fail(f"blocked default must not read candidate emotion for {trade_date}"),
    )

    payload = market_monitor.build_market_monitor_eod()

    assert payload["trade_date"] == ""
    assert payload["strategy_signal_summary"]["topn_preview"] == []
    assert any("display trade date unavailable" in warning for warning in payload["warnings"])


def test_boundary_disabled_keeps_legacy_latest_defaults(monkeypatch):
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from=""),
    )
    summary = {"latest_market_date": "2026-07-21"}

    assert display_date_gate.resolve_default_trade_date(summary)["trade_date"] == "2026-07-21"

    monkeypatch.setattr(daily_review_lite, "load_platform_summary", lambda service: summary)
    monkeypatch.setattr(daily_review_lite, "_latest_registered_run", lambda trade_date, service: {"run_id": trade_date})
    monkeypatch.setattr(
        daily_review_lite,
        "_load_payload_from_run",
        lambda run, selected_trade_date: {"trade_date": selected_trade_date},
    )
    assert daily_review_lite.build_daily_review_lite(service="test")["trade_date"] == "2026-07-21"


def test_explicit_dates_bypass_default_resolver(monkeypatch):
    monkeypatch.setattr(
        display_date_gate,
        "SETTINGS",
        SimpleNamespace(browser_acceptance_required_from="2026-07-21"),
    )
    monkeypatch.setattr(
        display_date_gate,
        "load_recent_data_run_manifest",
        lambda **_kwargs: pytest.fail("explicit dates must not load display-gate manifests"),
    )
    monkeypatch.setattr(daily_review_lite, "load_platform_summary", lambda service: {})
    monkeypatch.setattr(daily_review_lite, "_latest_registered_run", lambda trade_date, service: {"run_id": trade_date})
    monkeypatch.setattr(
        daily_review_lite,
        "_load_payload_from_run",
        lambda run, selected_trade_date: {"trade_date": selected_trade_date},
    )

    assert daily_review_lite.build_daily_review_lite("2026-07-19", service="test")["trade_date"] == "2026-07-19"
    assert evidence_digest._selected_trade_date("2026-07-19", "manual_v1", []) == "2026-07-19"


def test_daily_review_route_cache_key_changes_with_rollout_boundary(monkeypatch):
    settings = SimpleNamespace(browser_acceptance_required_from="")
    monkeypatch.setattr(display_date_gate, "SETTINGS", settings)
    calls: list[str] = []

    def build_payload(trade_date=None):
        calls.append(settings.browser_acceptance_required_from)
        return {"trade_date": trade_date or settings.browser_acceptance_required_from or "legacy"}

    monkeypatch.setattr(dashboard_app, "build_daily_review_lite", build_payload)
    client = TestClient(dashboard_app.create_app())

    first = client.get("/api/daily-review-lite")
    settings.browser_acceptance_required_from = "2026-07-21"
    second = client.get("/api/daily-review-lite")

    assert first.json()["trade_date"] == "legacy"
    assert second.json()["trade_date"] == "2026-07-21"
    assert calls == ["", "2026-07-21"]
