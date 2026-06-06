from __future__ import annotations

import pytest

from stock_research.research_infra.feature_registry import (
    FeatureRecord,
    FeatureRegistryValidationError,
    export_feature_registry,
    get_feature_record,
    list_feature_records,
)


def test_feature_registry_exports_existing_factor_metadata() -> None:
    ret_20 = get_feature_record("ret_20")

    assert ret_20.feature_name == "ret_20"
    assert ret_20.category == "factor"
    assert ret_20.input_source == "custom"
    assert ret_20.point_in_time_rule == "uses market data available on or before trade_date"
    assert ret_20.lookback_window == "20d"
    assert ret_20.leakage_risk == "low"
    assert ret_20.owner_module == "stock_research.factor_registry"
    assert "factor_eval" in ret_20.downstream_usage


def test_feature_registry_includes_research_and_news_signal_records() -> None:
    records = {record.feature_name: record for record in list_feature_records()}

    assert records["research_support_score"].category == "research_coverage"
    assert records["research_support_score"].input_source == "stock_report/pdf/manual_review"
    assert records["research_support_score"].leakage_risk == "medium"
    assert records["coverage_freshness_score"].category == "research_coverage"
    assert records["public_news_sentiment_score"].category == "news"
    assert records["public_news_sentiment_score"].point_in_time_rule == (
        "uses public news with availability_timestamp <= trade_date close"
    )


def test_feature_registry_exports_jsonable_sorted_records() -> None:
    exported = export_feature_registry(["research_support_score", "ret_20"])

    assert [record["feature_name"] for record in exported] == [
        "research_support_score",
        "ret_20",
    ]
    assert exported[0]["category"] == "research_coverage"
    assert exported[1]["lookback_window"] == "20d"


def test_feature_record_requires_point_in_time_rule_and_valid_leakage_risk() -> None:
    with pytest.raises(FeatureRegistryValidationError) as exc:
        FeatureRecord(
            feature_name="unsafe_future_return",
            category="factor",
            input_source="future_returns",
            point_in_time_rule="",
            lookback_window="5d",
            leakage_risk="unsafe",
            owner_module="tests",
            downstream_usage=["unit_test"],
            availability_start_date=None,
            status="draft",
        )

    message = str(exc.value)
    assert "point_in_time_rule" in message
    assert "leakage_risk" in message
