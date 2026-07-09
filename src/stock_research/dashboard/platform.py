from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.read_models import build_platform_summary_read_model


def load_platform_summary(
    score_version: str = "manual_v1",
    top_n: int = 5,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    return build_platform_summary_read_model(
        score_version=score_version,
        top_n=top_n,
        service=service,
    )
