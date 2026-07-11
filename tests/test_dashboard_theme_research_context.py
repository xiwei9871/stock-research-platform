from __future__ import annotations

from copy import deepcopy

from stock_research.dashboard import theme_research_context
from stock_research.dashboard.theme_research_context import (
    build_daily_theme_research_digest,
    build_asset_theme_context,
    build_theme_research_updates,
    load_asset_theme_context,
    list_theme_research_updates,
    normalize_theme_research_company_code,
)
from stock_research.theme_research_priority import (
    load_theme_research_priority_package,
)


def _context() -> dict:
    return deepcopy(load_theme_research_priority_package())


def test_company_code_normalization_supports_platform_asset_identifiers() -> None:
    assert normalize_theme_research_company_code("CN:SZ:300870") == "300870.SZ"
    assert normalize_theme_research_company_code("300870.SZ") == "300870.SZ"
    assert normalize_theme_research_company_code("sz300870") == "300870.SZ"
    assert normalize_theme_research_company_code("CN:SH:600000") == "600000.SH"
    assert normalize_theme_research_company_code("830799.BJ") == "830799.BJ"
    assert normalize_theme_research_company_code("missing") == ""


def test_asset_context_uses_company_scoped_database_loader(monkeypatch) -> None:
    context = _context()
    captured = {}

    def scoped_loader(company_code, *, service=None):
        captured["call"] = {"company_code": company_code, "service": service}
        return context

    monkeypatch.setattr(theme_research_context, "load_asset_db_context", scoped_loader)
    monkeypatch.setattr(
        theme_research_context,
        "load_db_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("asset context must not load the full database package")
        ),
    )

    payload = load_asset_theme_context("CN:SZ:002837", service="runtime")

    assert payload["status"] == "reviewed_context_available"
    assert captured["call"] == {"company_code": "002837.SZ", "service": "runtime"}


def test_reviewed_mapping_builds_evidence_backed_research_context() -> None:
    payload = build_asset_theme_context("CN:SZ:002837", _context())

    assert payload["asset_id"] == "CN:SZ:002837"
    assert payload["company_code"] == "002837.SZ"
    assert payload["status"] == "reviewed_context_available"
    assert payload["driver_assessment"] == "mixed_or_uncertain"
    assert payload["theme_count"] == 1
    assert payload["mapping_count"] == 1
    assert payload["evidence_gap_count"] == 0
    assert payload["research_only"] is True
    assert payload["used_for_signal"] is False
    assert payload["used_for_admission"] is False

    theme = payload["themes"][0]
    assert theme["theme_id"] == "ai_power_value_capture_v1"
    assert theme["dashboard_path"] == "/theme-research/ai_power_value_capture_v1"

    mapping = payload["mappings"][0]
    assert mapping["mapping_id"] == "ai_power_liquid_cooling_002837_v1"
    assert mapping["review_status"] == "reviewed"
    assert mapping["node"]["node_id"] == "liquid_cooling"
    assert mapping["node"]["node_review_status"] == "reviewed"
    assert mapping["node"]["value_capture_score"] == 5
    assert mapping["node"]["bottleneck_score"] == 4
    assert mapping["evidence_items"]
    assert all(item["source"]["review_status"] == "accepted" for item in mapping["evidence_items"])
    assert all(claim["platform_use_status"] == "reviewed" for claim in mapping["reviewed_claims"])


def test_unmapped_company_returns_valid_empty_context() -> None:
    payload = build_asset_theme_context("CN:SZ:000001", _context())

    assert payload["status"] == "not_mapped"
    assert payload["driver_assessment"] == "insufficient_evidence"
    assert payload["themes"] == []
    assert payload["mappings"] == []
    assert payload["excluded_mappings"] == []
    assert payload["warnings"] == []


def test_mapping_eligibility_fails_closed_with_explicit_reasons() -> None:
    context = _context()
    mapping = next(
        row
        for row in context["mapping_package"]["company_mappings"]
        if row["company_code"] == "002837.SZ"
    )
    mapping["review_status"] = "draft"

    payload = build_asset_theme_context("002837.SZ", context)

    assert payload["status"] == "evidence_gap"
    assert payload["mappings"] == []
    assert payload["evidence_gap_count"] == 1
    assert payload["excluded_mappings"] == [
        {
            "mapping_id": "ai_power_liquid_cooling_002837_v1",
            "theme_id": "ai_power_value_capture_v1",
            "node_id": "liquid_cooling",
            "reasons": ["mapping_not_reviewed"],
        }
    ]


def test_draft_theme_is_excluded_even_when_mapping_node_and_evidence_are_reviewed() -> None:
    context = _context()
    theme = next(
        row
        for row in context["theme_package"]["themes"]
        if row["theme_id"] == "ai_power_value_capture_v1"
    )
    theme["status"] = "draft"

    payload = build_asset_theme_context("002837.SZ", context)

    assert payload["status"] == "evidence_gap"
    assert payload["mappings"] == []
    assert payload["excluded_mappings"][0]["reasons"] == ["theme_not_reviewed"]


def test_mapping_with_unaccepted_evidence_source_is_excluded() -> None:
    context = _context()
    source = next(
        row
        for row in context["mapping_package"]["sources"]
        if row["source_id"] == "ai_power_envicool_2025_annual_report"
    )
    source["review_status"] = "needs_full_text"

    payload = build_asset_theme_context("002837.SZ", context)

    assert payload["status"] == "evidence_gap"
    assert payload["mappings"] == []
    assert payload["excluded_mappings"][0]["reasons"] == [
        "mapping_evidence_source_not_accepted"
    ]


def test_reviewed_updates_filter_status_date_and_sort_stably() -> None:
    review_events = [
        {
            "review_event_id": "review-2",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "claim",
            "object_id": "claim-reviewed",
            "from_status": "draft",
            "to_status": "reviewed",
            "decision": "accept",
            "comment": "verified",
            "created_at": "2026-07-11T09:00:00+08:00",
        },
        {
            "review_event_id": "review-1",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "source",
            "object_id": "source-lead",
            "from_status": "unknown",
            "to_status": "lead_only",
            "decision": "lead",
            "comment": "not evidence",
            "created_at": "2026-07-11T10:00:00+08:00",
        },
        {
            "review_event_id": "review-old",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "node",
            "object_id": "old-node",
            "from_status": "draft",
            "to_status": "reviewed",
            "decision": "accept",
            "comment": "old",
            "created_at": "2026-07-09T10:00:00+08:00",
        },
    ]
    revisions = [
        {
            "revision_id": "revision-1",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "company_mappings",
            "object_id": "mapping-reviewed",
            "operation": "update",
            "after_payload": {"review_status": "reviewed"},
            "created_at": "2026-07-11T11:00:00+08:00",
        }
    ]

    payload = build_theme_research_updates(
        review_events,
        revisions,
        since="2026-07-10",
        limit=10,
    )

    assert [row["update_id"] for row in payload["items"]] == [
        "revision-1",
        "review-2",
    ]
    assert payload["total"] == 2
    assert payload["by_object_type"] == {"claim": 1, "company_mapping": 1}
    assert payload["research_only"] is True
    assert payload["used_for_signal"] is False


def test_reviewed_updates_drop_stale_approval_after_later_revocation() -> None:
    review_events = [
        {
            "review_event_id": "accepted",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "source",
            "object_id": "source-1",
            "from_status": "unknown",
            "to_status": "accepted",
            "decision": "accept",
            "comment": "accepted",
            "created_at": "2026-07-11T09:00:00+08:00",
        },
        {
            "review_event_id": "rejected",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "source",
            "object_id": "source-1",
            "from_status": "accepted",
            "to_status": "rejected",
            "decision": "reject",
            "comment": "revoked",
            "created_at": "2026-07-11T10:00:00+08:00",
        },
    ]

    payload = build_theme_research_updates(
        review_events,
        [],
        since="2026-07-11",
        until="2026-07-12",
        limit=10,
    )

    assert payload["items"] == []
    assert payload["total"] == 0


def test_reviewed_updates_include_latest_reviewed_theme_revision() -> None:
    revisions = [
        {
            "revision_id": "theme-review",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "themes",
            "object_id": "ai_power_value_capture_v1",
            "operation": "update",
            "after_payload": {
                "status": "reviewed",
                "theme_name": "AI供电产业链：谁在拿走价值量",
            },
            "created_at": "2026-07-11T12:00:00+08:00",
        }
    ]

    payload = build_theme_research_updates([], revisions, limit=10)

    assert payload["items"] == [
        {
            "update_id": "theme-review",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "theme",
            "object_id": "ai_power_value_capture_v1",
            "from_status": "",
            "to_status": "reviewed",
            "decision": "update",
            "summary": "AI供电产业链：谁在拿走价值量",
            "created_at": "2026-07-11T12:00:00+08:00",
        }
    ]


def test_update_window_uses_explicit_end_boundary() -> None:
    events = [
        {
            "review_event_id": "inside",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "claim",
            "object_id": "claim-1",
            "from_status": "draft",
            "to_status": "reviewed",
            "decision": "accept",
            "comment": "inside",
            "created_at": "2026-07-11T23:59:59+08:00",
        },
        {
            "review_event_id": "outside",
            "theme_id": "ai_power_value_capture_v1",
            "object_type": "claim",
            "object_id": "claim-2",
            "from_status": "draft",
            "to_status": "reviewed",
            "decision": "accept",
            "comment": "outside",
            "created_at": "2026-07-12T00:00:00+08:00",
        },
    ]

    payload = build_theme_research_updates(
        events,
        [],
        since="2026-07-11",
        until="2026-07-12",
        limit=10,
    )

    assert [row["update_id"] for row in payload["items"]] == ["inside"]


def test_updates_reject_invalid_since_and_limit() -> None:
    for since, limit in (("not-a-date", 10), (None, 0), (None, 501)):
        try:
            build_theme_research_updates([], [], since=since, limit=limit)
        except ValueError as exc:
            assert str(exc) in {"theme_research_since_invalid", "theme_research_limit_invalid"}
        else:
            raise AssertionError("invalid update request must fail")


def test_daily_digest_counts_reviewed_workflow_context() -> None:
    updates = {
        "total": 2,
        "items": [],
        "by_object_type": {"claim": 1, "node": 1},
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "warnings": [],
    }

    digest = build_daily_theme_research_digest(
        "2026-07-11",
        context=_context(),
        updates=updates,
    )

    assert digest["status"] == "ready"
    assert digest["reviewed_theme_count"] == 1
    assert digest["mapped_company_count"] == 2
    assert digest["reviewed_mapping_count"] == 2
    assert digest["recent_reviewed_update_count"] == 2
    assert digest["evidence_gap_count"] == 15
    assert digest["mapped_companies"][0]["company_code"] == "002837.SZ"
    assert digest["mapped_companies"][0]["theme_name"] == "AI供电产业链：谁在拿走价值量"
    assert digest["research_only"] is True
    assert digest["used_for_admission"] is False


def test_daily_digest_requests_one_shanghai_calendar_day(monkeypatch) -> None:
    captured = {}

    def updates_loader(*, since=None, until=None, limit=100, service=None):
        captured.update({"since": since, "until": until, "limit": limit})
        return {"total": 0, "items": []}

    monkeypatch.setattr(theme_research_context, "list_theme_research_updates", updates_loader)

    build_daily_theme_research_digest("2026-07-11", context=_context())

    assert captured == {
        "since": "2026-07-11T00:00:00+08:00",
        "until": "2026-07-12T00:00:00+08:00",
        "limit": 100,
    }


def test_update_queries_filter_reviewed_rows_before_limit(monkeypatch) -> None:
    queries = []

    class ConnectionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_fetch_all(conn, sql, params):
        queries.append(" ".join(sql.split()))
        return []

    monkeypatch.setattr(theme_research_context, "connect", lambda service: ConnectionContext())
    monkeypatch.setattr(theme_research_context, "fetch_all", fake_fetch_all)

    payload = list_theme_research_updates(since="2026-07-01", limit=20, service="test")

    assert payload["total"] == 0
    assert "DISTINCT ON (object_type, object_id)" in queries[0]
    assert "DISTINCT ON (object_id)" in queries[1]
    assert all("LIMIT %s" in query for query in queries)
