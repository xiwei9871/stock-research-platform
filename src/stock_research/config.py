from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    research_service: str = "stock_research"
    hfq_service: str = "stock_hfq"
    qfq_service: str = "stock_qfq"
    default_market: str = "CN_A"
    default_currency: str = "CNY"
    selection_top_n: int = 20


SETTINGS = Settings()
