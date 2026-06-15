from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import evidence_digest


def _profile(asset_id="000001.SZ", *, rank=3, risk_tags=None):
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "asset": {"asset_id": asset_id, "symbol": asset_id[:6], "name": "平安银行"},
        "score": {
            "trade_date": "2026-06-12",
            "asset_id": asset_id,
            "rank": rank,
            "score_total": 88.5,
            "score_version": "manual_v1",
            "score_components": {},
        },
        "signals": [
            {
                "asset_id": asset_id,
                "primary_signal": "candidate",
                "risk_tags": risk_tags or [],
                "signal_tags": ["momentum"],
            }
        ],
        "bars": [],
        "decisions": [],
        "outcomes": [],
        "factor_values": [],
        "coverage": {},
    }


def _news(asset_id="000001.SZ", *, items=2):
    return {
        "asset_id": asset_id,
        "summary": {
            "news_count_1d": min(items, 1),
            "news_count_3d": min(items, 2),
            "news_count_7d": items,
            "latest_published_at": "2026-06-12T09:30:00+08:00",
        },
        "items": [
            {
                "news_id": "news-1",
                "title": "平安银行经营更新",
                "quality_score": 82,
                "published_at": "2026-06-12T09:30:00+08:00",
            }
        ][:items],
        "warnings": [],
    }


def _reports(asset_id="000001.SZ", *, count=1):
    return {
        "asset_id": asset_id,
        "summary": {
            "report_count_30d": count,
            "report_count_90d": count,
            "broker_coverage_count_90d": 1 if count else 0,
            "latest_report_date": "2026-06-10" if count else None,
            "latest_rating": "买入" if count else "",
            "latest_target_price": 19.5 if count else None,
        },
        "items": [
            {
                "report_id": "r1",
                "event_key": "r1:000001.SZ",
                "asset_id": asset_id,
                "ts_code": asset_id,
                "stock_name": "平安银行",
                "report_title": "平安银行深度报告",
                "rating": "买入",
                "target_price": 19.5,
                "broker": "华泰证券",
            }
        ][:count],
        "warnings": [],
    }


def _market(asset_id="000001.SZ", *, tab="limit_up"):
    empty = {"auction": [], "limit_up": [], "broken_limit_up": [], "limit_down": [], "auction_status": "available"}
    if tab:
        empty[tab] = [
            {
                "asset_id": asset_id,
                "name": "平安银行",
                "symbol": asset_id[:6],
                "tab": tab,
                "amount": 1000000000,
                "pct_chg": 10.0,
                "board": "main",
            }
        ]
    return {
        "trade_date": "2026-06-12",
        "emotion_stock_lists": empty,
        "strategy_signal_summary": {"topn_preview": []},
        "warnings": [],
    }


def _actions_by_key(digest):
    return {action["key"]: action for action in digest["next_actions"]}


def test_build_evidence_digest_strong_source_backed(monkeypatch):
    monkeypatch.setattr(
        evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"])
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_public_news_for_dashboard",
        lambda **kwargs: _news(kwargs["asset_id"]),
    )
    monkeypatch.setattr(
        evidence_digest,
        "list_research_reports",
        lambda **kwargs: _reports(kwargs["asset_id"]),
    )
    monkeypatch.setattr(
        evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab="limit_up")
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12"},
    )

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["canonical_asset_id"] == "000001.SZ"
    assert digest["bucket"] == "strong"
    assert digest["score"] >= 75
    assert any(fact["kind"] == "news" for fact in digest["facts"])
    assert any(fact["kind"] == "research" for fact in digest["facts"])
    assert digest["source_refs"]["news_id"] == "news-1"
    assert digest["source_refs"]["report_id"] == "r1"
    assert digest["source_refs"]["monitor_tab"] == "limit_up"
    assert digest["source_refs"]["strategy_asset_id"] == "000001.SZ"
    actions = _actions_by_key(digest)
    assert set(actions) >= {"open_news", "open_research", "open_market", "review_stock"}
    assert actions["open_news"]["news_id"] == "news-1"
    assert actions["open_research"]["report_id"] == "r1"
    assert actions["open_research"]["event_key"] == "r1:000001.SZ"
    assert actions["open_research"]["workspace"] == "researchReports"
    assert actions["open_market"]["monitor_tab"] == "limit_up"
    assert actions["review_stock"]["workspace"] == "stock"
    for action in actions.values():
        assert action["workspace"]
        assert action["asset_id"] == "000001.SZ"
        assert action["query"]


def test_build_evidence_digest_includes_lineage_and_available_sections(monkeypatch):
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"]))
    monkeypatch.setattr(evidence_digest, "load_public_news_for_dashboard", lambda **kwargs: _news(kwargs["asset_id"]))
    monkeypatch.setattr(evidence_digest, "list_research_reports", lambda **kwargs: _reports(kwargs["asset_id"]))
    monkeypatch.setattr(evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab="limit_up"))
    monkeypatch.setattr(
        evidence_digest,
        "load_latest_data_run_manifest",
        lambda trade_date=None: [
            {
                "run_id": "eod-2026-06-12-local",
                "trade_date": "2026-06-12",
                "latest_trade_date": "2026-06-12",
                "module": "news",
                "tier": "tier2",
                "status": "success",
                "warnings": [],
            }
        ],
        raising=False,
    )

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["stock_code"] == "000001.SZ"
    assert digest["stock_name"] == "平安银行"
    assert digest["latest_trade_date"] == "2026-06-12"
    assert digest["run_id"] == "eod-2026-06-12-local"
    assert digest["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert digest["generated_at"] == "2026-06-12T00:00:00+00:00"
    assert digest["overall_status"] == "OK"
    assert set(digest["sections"]) >= {
        "asset_profile",
        "score_snapshot",
        "factor_contributions",
        "strategy_context",
        "market_monitor",
        "news",
        "research_reports",
        "lhb",
        "industry",
        "financial",
        "technical_features",
        "generated_reports",
        "operator_history",
        "follow_up_history",
        "risk_flags",
    }
    assert digest["sections"]["asset_profile"]["status"] == "available"
    assert digest["sections"]["score_snapshot"]["status"] == "available"
    assert digest["sections"]["news"]["status"] == "available"
    assert digest["sections"]["research_reports"]["status"] == "available"
    assert digest["sections"]["financial"]["status"] == "skipped"
    assert digest["missing_evidence"] == []
    assert digest["partial_evidence"] == []
    assert digest["lineage"]["score_version"] == "manual_v1"
    assert digest["lineage"]["topn_rank"] == 3


def test_build_evidence_digest_marks_optional_source_failures_partial(monkeypatch):
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"]))
    monkeypatch.setattr(
        evidence_digest,
        "load_public_news_for_dashboard",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("news offline")),
    )
    monkeypatch.setattr(
        evidence_digest,
        "list_research_reports",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("reports offline")),
    )
    monkeypatch.setattr(evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab=None))
    monkeypatch.setattr(evidence_digest, "load_latest_data_run_manifest", lambda trade_date=None: [], raising=False)

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["overall_status"] == "PARTIAL"
    assert digest["sections"]["news"]["status"] == "partial"
    assert digest["sections"]["research_reports"]["status"] == "partial"
    assert "news" in digest["partial_evidence"]
    assert "research_reports" in digest["partial_evidence"]
    assert any("news offline" in warning for warning in digest["sections"]["news"]["warnings"])
    assert any("reports offline" in warning for warning in digest["sections"]["research_reports"]["warnings"])


def test_build_evidence_digest_marks_empty_optional_sources_missing(monkeypatch):
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"]))
    monkeypatch.setattr(evidence_digest, "load_public_news_for_dashboard", lambda **kwargs: _news(kwargs["asset_id"], items=0))
    monkeypatch.setattr(evidence_digest, "list_research_reports", lambda **kwargs: _reports(kwargs["asset_id"], count=0))
    monkeypatch.setattr(evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab=None))
    monkeypatch.setattr(evidence_digest, "load_latest_data_run_manifest", lambda trade_date=None: [], raising=False)

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["overall_status"] == "PARTIAL"
    assert digest["sections"]["news"]["status"] == "missing"
    assert digest["sections"]["research_reports"]["status"] == "missing"
    assert "news" in digest["missing_evidence"]
    assert "research_reports" in digest["missing_evidence"]


def test_build_evidence_digest_blocks_when_core_score_missing(monkeypatch):
    profile = _profile("000001.SZ")
    profile["score"] = {}
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: profile)
    monkeypatch.setattr(evidence_digest, "load_public_news_for_dashboard", lambda **kwargs: _news(kwargs["asset_id"]))
    monkeypatch.setattr(evidence_digest, "list_research_reports", lambda **kwargs: _reports(kwargs["asset_id"]))
    monkeypatch.setattr(evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab="limit_up"))
    monkeypatch.setattr(evidence_digest, "load_latest_data_run_manifest", lambda trade_date=None: [], raising=False)

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["overall_status"] == "BLOCKED"
    assert digest["sections"]["score_snapshot"]["status"] == "missing"
    assert "score_snapshot" in digest["missing_evidence"]


def test_build_evidence_digest_thin_when_sources_missing(monkeypatch):
    monkeypatch.setattr(
        evidence_digest,
        "build_asset_profile",
        lambda **kwargs: _profile(kwargs["asset_id"], rank=80),
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_public_news_for_dashboard",
        lambda **kwargs: _news(kwargs["asset_id"], items=0),
    )
    monkeypatch.setattr(
        evidence_digest,
        "list_research_reports",
        lambda **kwargs: _reports(kwargs["asset_id"], count=0),
    )
    monkeypatch.setattr(
        evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab=None)
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12"},
    )

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["bucket"] == "thin"
    assert any(flag["key"] == "thin_research" for flag in digest["risk_flags"])
    assert any(flag["key"] == "low_news_coverage" for flag in digest["risk_flags"])
    assert digest["source_refs"]["strategy_asset_id"] == "000001.SZ"
    actions = _actions_by_key(digest)
    assert set(actions) >= {"open_news", "open_research", "open_market", "review_stock"}
    assert actions["open_research"]["workspace"] == "researchReports"
    for action in actions.values():
        assert action["workspace"]
        assert action["asset_id"] == "000001.SZ"
        assert action["query"]


def test_build_evidence_digest_risk_heavy_for_market_pressure(monkeypatch):
    monkeypatch.setattr(
        evidence_digest,
        "build_asset_profile",
        lambda **kwargs: _profile(kwargs["asset_id"], risk_tags=["gap_risk"]),
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_public_news_for_dashboard",
        lambda **kwargs: _news(kwargs["asset_id"]),
    )
    monkeypatch.setattr(
        evidence_digest,
        "list_research_reports",
        lambda **kwargs: _reports(kwargs["asset_id"]),
    )
    monkeypatch.setattr(
        evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab="limit_down")
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12"},
    )

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["bucket"] == "risk_heavy"
    assert any(flag["key"] == "market_limit_down" for flag in digest["risk_flags"])
    assert any(flag["key"] == "strategy_risk_tags" for flag in digest["risk_flags"])


def test_build_evidence_digest_returns_warning_for_partial_source_failure(monkeypatch):
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"]))
    monkeypatch.setattr(
        evidence_digest,
        "load_public_news_for_dashboard",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("news offline")),
    )
    monkeypatch.setattr(
        evidence_digest,
        "list_research_reports",
        lambda **kwargs: _reports(kwargs["asset_id"]),
    )
    monkeypatch.setattr(
        evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab=None)
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12"},
    )

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert any("news offline" in warning for warning in digest["warnings"])
    assert any(fact["kind"] == "research" for fact in digest["facts"])


def test_build_evidence_digest_passes_explicit_date_windows(monkeypatch):
    captured = {"news": None, "research": None}
    monkeypatch.setattr(
        evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"])
    )

    def fake_news(**kwargs):
        captured["news"] = kwargs
        return _news(kwargs["asset_id"])

    def fake_reports(**kwargs):
        captured["research"] = kwargs
        return _reports(kwargs["asset_id"])

    monkeypatch.setattr(evidence_digest, "load_public_news_for_dashboard", fake_news)
    monkeypatch.setattr(evidence_digest, "list_research_reports", fake_reports)
    monkeypatch.setattr(
        evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab="limit_up")
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12"},
    )

    evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12", lookback_days=90)

    assert captured["news"]["asset_id"] == "000001.SZ"
    assert captured["news"]["start_time"] == "2026-06-06"
    assert captured["news"]["end_time"] == "2026-06-12T23:59:59+08:00"
    assert captured["news"]["limit"] == 5
    assert captured["research"]["asset_id"] == "000001.SZ"
    assert captured["research"]["start_date"] == "2026-03-15"
    assert captured["research"]["end_date"] == "2026-06-12"
    assert captured["research"]["limit"] == 5


def test_build_evidence_digest_warns_when_market_date_unavailable(monkeypatch):
    captured_profile = {}
    news_calls = []
    research_calls = []
    market_calls = []
    monkeypatch.setattr(evidence_digest, "load_platform_summary", lambda **kwargs: {"latest_market_date": ""})
    monkeypatch.setattr(
        evidence_digest,
        "build_asset_profile",
        lambda **kwargs: captured_profile.update(kwargs) or _profile(kwargs["asset_id"]),
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_public_news_for_dashboard",
        lambda **kwargs: news_calls.append(kwargs) or _news(kwargs["asset_id"], items=0),
    )
    monkeypatch.setattr(
        evidence_digest,
        "list_research_reports",
        lambda **kwargs: research_calls.append(kwargs) or _reports(kwargs["asset_id"], count=0),
    )
    monkeypatch.setattr(
        evidence_digest,
        "build_market_monitor_eod",
        lambda **kwargs: market_calls.append(kwargs) or _market(tab=None),
    )

    digest = evidence_digest.build_evidence_digest("000001.SZ")

    assert digest["trade_date"] == ""
    assert captured_profile["trade_date"] == ""
    assert captured_profile["start_date"] == ""
    assert any(warning == "market date unavailable" for warning in digest["warnings"])
    assert news_calls == []
    assert research_calls == []
    assert market_calls == []


def test_build_evidence_digest_handles_platform_date_failure(monkeypatch):
    captured_profile = {}
    news_calls = []
    research_calls = []
    market_calls = []
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("platform offline")),
    )
    monkeypatch.setattr(
        evidence_digest,
        "build_asset_profile",
        lambda **kwargs: captured_profile.update(kwargs) or _profile(kwargs["asset_id"]),
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_public_news_for_dashboard",
        lambda **kwargs: news_calls.append(kwargs) or _news(kwargs["asset_id"], items=0),
    )
    monkeypatch.setattr(
        evidence_digest,
        "list_research_reports",
        lambda **kwargs: research_calls.append(kwargs) or _reports(kwargs["asset_id"], count=0),
    )
    monkeypatch.setattr(
        evidence_digest,
        "build_market_monitor_eod",
        lambda **kwargs: market_calls.append(kwargs) or _market(tab=None),
    )

    digest = evidence_digest.build_evidence_digest("000001.SZ")

    assert digest["trade_date"] == ""
    assert captured_profile["trade_date"] == ""
    assert any("platform offline" in warning for warning in digest["warnings"])
    assert any(warning == "market date unavailable" for warning in digest["warnings"])
    assert news_calls == []
    assert research_calls == []
    assert market_calls == []


def test_build_evidence_digest_high_rank_without_source_facts_is_not_strong(monkeypatch):
    monkeypatch.setattr(
        evidence_digest,
        "build_asset_profile",
        lambda **kwargs: _profile(kwargs["asset_id"], rank=1),
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_public_news_for_dashboard",
        lambda **kwargs: _news(kwargs["asset_id"], items=0),
    )
    monkeypatch.setattr(
        evidence_digest,
        "list_research_reports",
        lambda **kwargs: _reports(kwargs["asset_id"], count=0),
    )
    monkeypatch.setattr(
        evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab=None)
    )
    monkeypatch.setattr(
        evidence_digest,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12"},
    )

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["score"] >= 75
    assert digest["bucket"] == "thin"


def test_evidence_digest_endpoint_forwards_query(monkeypatch):
    captured = {}

    def fake_digest(asset_id, *, trade_date=None, lookback_days=90, score_version="manual_v1"):
        captured.update(
            {
                "asset_id": asset_id,
                "trade_date": trade_date,
                "lookback_days": lookback_days,
                "score_version": score_version,
            }
        )
        return {
            "asset_id": asset_id,
            "canonical_asset_id": asset_id,
            "trade_date": trade_date,
            "title": "Thin evidence",
            "score": 20,
            "bucket": "thin",
            "facts": [],
            "risk_flags": [],
            "source_refs": {},
            "next_actions": [],
            "warnings": [],
        }

    monkeypatch.setattr(dashboard_app, "build_evidence_digest", fake_digest, raising=False)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/evidence-digest?asset_id=000001.SZ&trade_date=2026-06-12&lookback_days=30&score_version=manual_v2"
    )

    assert response.status_code == 200
    assert captured == {
        "asset_id": "000001.SZ",
        "trade_date": "2026-06-12",
        "lookback_days": 30,
        "score_version": "manual_v2",
    }
    assert response.json()["bucket"] == "thin"
