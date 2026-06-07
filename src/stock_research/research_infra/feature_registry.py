from __future__ import annotations

from dataclasses import asdict, dataclass

from stock_research.factor_registry import list_factor_metadata


VALID_FEATURE_CATEGORIES = {
    "technical",
    "factor",
    "text",
    "news",
    "industry_regime",
    "market_regime",
    "research_coverage",
    "event",
}

VALID_LEAKAGE_RISKS = {
    "low",
    "medium",
    "high",
    "blocked",
}


class FeatureRegistryValidationError(ValueError):
    """Raised when a feature registry record is invalid."""


@dataclass(frozen=True)
class FeatureRecord:
    feature_name: str
    category: str
    input_source: str
    point_in_time_rule: str
    lookback_window: str
    leakage_risk: str
    owner_module: str
    downstream_usage: list[str]
    availability_start_date: str | None
    status: str

    def __post_init__(self) -> None:
        missing = [
            field_name
            for field_name in [
                "feature_name",
                "category",
                "input_source",
                "point_in_time_rule",
                "lookback_window",
                "leakage_risk",
                "owner_module",
                "status",
            ]
            if not str(getattr(self, field_name)).strip()
        ]
        if self.category not in VALID_FEATURE_CATEGORIES:
            missing.append("category")
        if self.leakage_risk not in VALID_LEAKAGE_RISKS:
            missing.append("leakage_risk")
        if not self.downstream_usage:
            missing.append("downstream_usage")
        if missing:
            raise FeatureRegistryValidationError(
                "invalid feature registry fields: " + ", ".join(sorted(set(missing)))
            )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_feature_record(feature_name: str) -> FeatureRecord:
    registry = _registry_map()
    normalized = str(feature_name)
    if normalized not in registry:
        raise KeyError(f"unknown feature registry record: {feature_name}")
    return registry[normalized]


def list_feature_records(
    feature_names: list[str] | tuple[str, ...] | None = None,
) -> list[FeatureRecord]:
    registry = _registry_map()
    names = (
        sorted(registry)
        if feature_names is None
        else [str(name) for name in feature_names]
    )
    return [get_feature_record(name) for name in names]


def export_feature_registry(
    feature_names: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, object]]:
    return [record.to_dict() for record in list_feature_records(feature_names)]


def _registry_map() -> dict[str, FeatureRecord]:
    records = [
        *_factor_feature_records(),
        *_manual_research_signal_records(),
    ]
    return {record.feature_name: record for record in records}


def _factor_feature_records() -> list[FeatureRecord]:
    return [
        FeatureRecord(
            feature_name=metadata.factor_name,
            category="factor",
            input_source=metadata.source,
            point_in_time_rule=_factor_point_in_time_rule(metadata.source),
            lookback_window=_infer_lookback_window(metadata.factor_name),
            leakage_risk=_factor_leakage_risk(metadata.source),
            owner_module="stock_research.factor_registry",
            downstream_usage=["factor_pipeline", "factor_eval", "topn_scoring"],
            availability_start_date=metadata.availability_start_date,
            status=metadata.status,
        )
        for metadata in list_factor_metadata()
    ]


def _manual_research_signal_records() -> list[FeatureRecord]:
    return [
        FeatureRecord(
            feature_name="research_support_score",
            category="research_coverage",
            input_source="stock_report/pdf/manual_review",
            point_in_time_rule=(
                "uses report and review evidence with availability_timestamp <= trade_date close"
            ),
            lookback_window="90d",
            leakage_risk="medium",
            owner_module="stock_research.research_infra.feature_registry",
            downstream_usage=["mid_trend_review", "watchlist_review", "topn_overlay"],
            availability_start_date=None,
            status="draft",
        ),
        FeatureRecord(
            feature_name="coverage_freshness_score",
            category="research_coverage",
            input_source="stock_report/pdf/manual_review",
            point_in_time_rule=(
                "uses latest coverage timestamp with availability_timestamp <= trade_date close"
            ),
            lookback_window="90d",
            leakage_risk="medium",
            owner_module="stock_research.research_infra.feature_registry",
            downstream_usage=["mid_trend_review", "watchlist_review"],
            availability_start_date=None,
            status="draft",
        ),
        FeatureRecord(
            feature_name="public_news_sentiment_score",
            category="news",
            input_source="public_news/fallback_news",
            point_in_time_rule="uses public news with availability_timestamp <= trade_date close",
            lookback_window="7d",
            leakage_risk="medium",
            owner_module="stock_research.research_infra.feature_registry",
            downstream_usage=["topn_overlay", "watchlist_review"],
            availability_start_date=None,
            status="draft",
        ),
    ]


def _factor_point_in_time_rule(source: str) -> str:
    if str(source) == "fundamental":
        return "uses financial rows with announcement_date <= trade_date"
    return "uses market data available on or before trade_date"


def _factor_leakage_risk(source: str) -> str:
    if str(source) == "fundamental":
        return "medium"
    return "low"


def _infer_lookback_window(feature_name: str) -> str:
    parts = str(feature_name).split("_")
    numeric_parts = [part for part in parts if part.isdigit()]
    if numeric_parts:
        return f"{numeric_parts[-1]}d"
    if str(feature_name).endswith("_ttm"):
        return "ttm"
    return "configured"
