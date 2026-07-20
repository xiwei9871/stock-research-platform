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
