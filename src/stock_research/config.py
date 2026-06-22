import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    research_service: str = "stock_research"
    hfq_service: str = "stock_hfq"
    qfq_service: str = "stock_qfq"
    default_market: str = "CN_A"
    default_currency: str = "CNY"
    selection_top_n: int = 20
    dashboard_session_cookie_name: str = os.getenv(
        "STOCK_RESEARCH_SESSION_COOKIE",
        "stock_research_session",
    )
    dashboard_csrf_cookie_name: str = os.getenv(
        "STOCK_RESEARCH_CSRF_COOKIE",
        "stock_research_csrf",
    )
    dashboard_session_ttl_hours: int = int(
        os.getenv("STOCK_RESEARCH_SESSION_TTL_HOURS", "168")
    )
    dashboard_secure_cookies: bool = (
        os.getenv("STOCK_RESEARCH_SECURE_COOKIES", "0") == "1"
    )


SETTINGS = Settings()
