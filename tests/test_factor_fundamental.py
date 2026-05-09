import pandas as pd
import pytest

from stock_research.factors import growth, quality


def test_compute_growth_factors_uses_report_metrics():
    frame = pd.DataFrame(
        [{"asset_id": "A", "revenue_yoy": 0.2, "np_yoy": 0.3, "deduct_np_yoy": 0.25}]
    )

    result = growth.compute_growth_factors(frame)

    assert result.iloc[0]["revenue_yoy"] == pytest.approx(0.2)
    assert result.iloc[0]["np_parent_yoy"] == pytest.approx(0.3)
    assert result.iloc[0]["deduct_np_yoy"] == pytest.approx(0.25)


def test_compute_quality_factors_uses_report_metrics():
    frame = pd.DataFrame(
        [{"asset_id": "A", "roe": 0.15, "roa": 0.08, "gross_margin": 0.4, "net_margin": 0.1, "debt_ratio": 0.35, "ocf_to_np": 1.2}]
    )

    result = quality.compute_quality_factors(frame)

    assert result.iloc[0]["roe"] == pytest.approx(0.15)
    assert result.iloc[0]["ocf_to_np"] == pytest.approx(1.2)
    assert result.iloc[0]["debt_ratio"] == pytest.approx(0.35)
