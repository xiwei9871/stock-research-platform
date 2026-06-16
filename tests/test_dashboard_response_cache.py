from stock_research.dashboard.response_cache import DashboardResponseCache


def test_dashboard_response_cache_reuses_payload_within_ttl():
    now = 100.0
    calls = []
    cache = DashboardResponseCache(ttl_seconds=30, clock=lambda: now)

    def load_payload():
        calls.append("load")
        return {"items": [len(calls)]}

    first = cache.get_or_set(("platform_summary", "manual_v1", 5), load_payload)
    second = cache.get_or_set(("platform_summary", "manual_v1", 5), load_payload)

    assert len(calls) == 1
    assert first == {"items": [1]}
    assert second == {"items": [1]}


def test_dashboard_response_cache_expires_by_ttl():
    current_time = {"value": 100.0}
    calls = []
    cache = DashboardResponseCache(ttl_seconds=10, clock=lambda: current_time["value"])

    def load_payload():
        calls.append("load")
        return {"calls": len(calls)}

    first = cache.get_or_set(("review_queue", "2026-06-12"), load_payload)
    current_time["value"] = 111.0
    second = cache.get_or_set(("review_queue", "2026-06-12"), load_payload)

    assert len(calls) == 2
    assert first == {"calls": 1}
    assert second == {"calls": 2}


def test_dashboard_response_cache_returns_copies_for_cached_payloads():
    cache = DashboardResponseCache(ttl_seconds=30, clock=lambda: 100.0)

    first = cache.get_or_set(("market_monitor", "2026-06-12"), lambda: {"items": [{"name": "原始"}]})
    first["items"][0]["name"] = "调用方修改"
    second = cache.get_or_set(("market_monitor", "2026-06-12"), lambda: {"items": [{"name": "不应执行"}]})

    assert second == {"items": [{"name": "原始"}]}
