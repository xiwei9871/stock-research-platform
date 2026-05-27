import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.factor_eval.validation_review import (
    build_factor_validation_review,
    write_factor_validation_review,
)


def _factor_rows() -> pd.DataFrame:
    rows = []
    for trade_date in ["2026-01-01", "2026-01-02", "2026-02-01", "2026-02-02"]:
        for asset_id, value in [("A", 1.0), ("B", 2.0), ("C", 3.0)]:
            rows.append({"trade_date": trade_date, "asset_id": asset_id, "factor_value": value})
    return pd.DataFrame(rows)


def _return_rows(*, out_sample_weak: bool = False) -> pd.DataFrame:
    rows = []
    for trade_date in ["2026-01-01", "2026-01-02"]:
        for asset_id, value in [("A", 0.01), ("B", 0.02), ("C", 0.03)]:
            rows.append({"trade_date": trade_date, "asset_id": asset_id, "forward_return_5d": value})
    out_values = [("A", 0.03), ("B", 0.02), ("C", 0.01)] if out_sample_weak else [("A", 0.01), ("B", 0.02), ("C", 0.03)]
    for trade_date in ["2026-02-01", "2026-02-02"]:
        for asset_id, value in out_values:
            rows.append({"trade_date": trade_date, "asset_id": asset_id, "forward_return_5d": value})
    return pd.DataFrame(rows)


def _segments() -> pd.DataFrame:
    rows = []
    for trade_date in ["2026-01-01", "2026-01-02", "2026-02-01", "2026-02-02"]:
        for asset_id, state in [("A", "weak"), ("B", "neutral"), ("C", "strong")]:
            rows.append({"trade_date": trade_date, "asset_id": asset_id, "market_state": state})
    return pd.DataFrame(rows)


def test_build_factor_validation_review_approves_when_sample_out_and_segments_pass():
    review = build_factor_validation_review(
        factors=_factor_rows(),
        returns=_return_rows(),
        factor_name="demo_factor",
        horizons=[5],
        split_date="2026-02-01",
        segments=_segments(),
        segment_col="market_state",
        min_abs_mean_ic=0.5,
        min_icir=0.0,
        min_ic_count=2,
    )

    assert review["approval"]["status"] == "approved_candidate"
    assert review["in_sample_gate"]["status"] == "approved"
    assert review["out_of_sample_gate"]["status"] == "approved"
    assert review["decay"]["primary_horizon"] == 5
    assert review["segment_validation"]["segment_col"] == "market_state"


def test_build_factor_validation_review_rejects_when_sample_out_fails():
    review = build_factor_validation_review(
        factors=_factor_rows(),
        returns=_return_rows(out_sample_weak=True),
        factor_name="demo_factor",
        horizons=[5],
        split_date="2026-02-01",
        min_abs_mean_ic=0.5,
        min_icir=0.0,
        min_ic_count=2,
    )

    assert review["approval"]["status"] == "rejected"
    assert review["out_of_sample_gate"]["status"] == "approved"
    assert review["approval"]["reason"] == "sample_out_direction_flip"


def test_write_factor_validation_review_outputs_json_markdown_and_decay_csv(tmp_path):
    review = build_factor_validation_review(
        factors=_factor_rows(),
        returns=_return_rows(),
        factor_name="demo_factor",
        horizons=[5],
        split_date="2026-02-01",
        segments=_segments(),
        segment_col="market_state",
        min_abs_mean_ic=0.5,
        min_icir=0.0,
        min_ic_count=2,
    )

    paths = write_factor_validation_review(review, output_dir=tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    decay = pd.read_csv(paths["decay_csv_path"])

    assert payload["factor_name"] == "demo_factor"
    assert payload["approval"]["status"] == "approved_candidate"
    assert "样本外" in markdown
    assert decay["horizon"].tolist() == [5]
