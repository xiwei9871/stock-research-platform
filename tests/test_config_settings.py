from stock_research.config import Settings


def test_settings_reads_research_service_from_environment(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_SERVICE", " stock_research_e2e_test ")

    assert Settings().research_service == "stock_research_e2e_test"


def test_settings_uses_default_research_service_when_environment_is_empty(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_SERVICE", "   ")

    assert Settings().research_service == "stock_research"


def test_settings_keeps_adjusted_price_services_constant(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_SERVICE", "stock_research_e2e_test")

    settings = Settings()

    assert settings.hfq_service == "stock_hfq"
    assert settings.qfq_service == "stock_qfq"


def test_browser_acceptance_rollout_boundary_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM", raising=False)

    assert Settings().browser_acceptance_required_from == ""


def test_browser_acceptance_rollout_boundary_reads_environment(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM", "2026-07-21")

    assert Settings().browser_acceptance_required_from == "2026-07-21"


def test_eod_browser_acceptance_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED", raising=False)

    assert Settings().eod_browser_acceptance_enabled is False


def test_eod_browser_acceptance_reads_true_values(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED", "true")

    assert Settings().eod_browser_acceptance_enabled is True


def test_eod_browser_acceptance_invalid_value_fails_safe(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED", "sometimes")

    assert Settings().eod_browser_acceptance_enabled is False
