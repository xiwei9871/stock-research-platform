from __future__ import annotations

from stock_research.research_project_v2_1.acquisition_browser import (
    OptionalBrowserProvider,
    detect_browser_runtime,
)
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.acquisition_contracts import (
    UnavailableSearchDiscoveryProvider,
)
import pytest


def test_browser_runtime_detection_returns_structured_unavailable_state() -> None:
    status = detect_browser_runtime(
        probe=lambda: (_ for _ in ()).throw(RuntimeError("missing runtime"))
    )
    assert status.available is False
    assert status.failure_code == "browser_runtime_unavailable"
    assert "missing runtime" not in status.diagnostic_summary


def test_browser_runtime_detection_reports_available_engine() -> None:
    status = detect_browser_runtime(probe=lambda: "chromium")
    assert status.available is True
    assert status.engine == "chromium"
    assert status.failure_code is None


def test_optional_browser_provider_does_not_silently_fetch_without_adapter() -> None:
    provider = OptionalBrowserProvider(runtime_probe=lambda: "chromium")
    result = provider.availability()
    assert result.available is True
    assert provider.can_acquire is False


def test_search_discovery_provider_has_structured_unavailable_state() -> None:
    provider = UnavailableSearchDiscoveryProvider()
    assert provider.status == "unavailable"
    assert provider.failure_code == "search_provider_error"
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        provider.search({"query_id": "query:fixture"})
    assert exc_info.value.details["failure_code"] == "search_provider_error"
