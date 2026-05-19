import json
from pathlib import Path

import pytest
import pandas as pd

from stock_research import factor_eval_batch


def test_run_factor_gate_batch_evaluates_and_stores_each_factor(monkeypatch):
    calls = []

    monkeypatch.setattr(
        factor_eval_batch,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.02]}),
        ),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "generate_multi_horizon_report",
        lambda **kwargs: {
            "factor_name": kwargs["factor_name"],
            "horizons": kwargs["horizons"],
            "reports": {
                5: {
                    "ic_summary": {
                        "mean_ic": 0.04,
                        "icir": 0.6,
                        "ic_count": 30,
                    }
                }
            },
        },
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "store_factor_eval_run",
        lambda **kwargs: calls.append(("run", kwargs)),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "store_factor_approval",
        lambda **kwargs: calls.append(("approval", kwargs)),
    )
    monkeypatch.setattr(factor_eval_batch, "_new_run_id", lambda factor_name: f"run-{factor_name}")

    result = factor_eval_batch.run_factor_gate_batch(
        factor_names=["alpha101_delta_close_1_rank", "gtja191_amount_momentum_5_10"],
        start_date="2026-01-01",
        end_date="2026-05-08",
        horizons=[5, 10, 20, 60],
        primary_horizon=5,
        calc_version="v1",
        score_version="manual_v1",
        quantiles=5,
        top_n=30,
    )

    assert list(result["factor_name"]) == [
        "alpha101_delta_close_1_rank",
        "gtja191_amount_momentum_5_10",
    ]
    assert list(result["status"]) == ["approved", "approved"]
    assert [kind for kind, _ in calls] == ["run", "approval", "run", "approval"]
    assert calls[0][1]["run_id"] == "run-alpha101_delta_close_1_rank"
    assert calls[1][1]["score_version"] == "manual_v1"


def test_run_factor_gate_batch_uses_default_candidates_when_factor_names_omitted(monkeypatch):
    calls = []

    monkeypatch.setattr(
        factor_eval_batch,
        "candidate_factor_names",
        lambda: ["ret_20", "qlib_ret_5"],
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.02]}),
        ),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "generate_multi_horizon_report",
        lambda **kwargs: {
            "factor_name": kwargs["factor_name"],
            "horizons": kwargs["horizons"],
            "reports": {
                5: {
                    "ic_summary": {
                        "mean_ic": 0.04,
                        "icir": 0.6,
                        "ic_count": 30,
                    }
                }
            },
        },
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "store_factor_eval_run",
        lambda **kwargs: calls.append(("run", kwargs)),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "store_factor_approval",
        lambda **kwargs: calls.append(("approval", kwargs)),
    )
    monkeypatch.setattr(factor_eval_batch, "_new_run_id", lambda factor_name: f"run-{factor_name}")

    result = factor_eval_batch.run_factor_gate_batch(
        factor_names=None,
        start_date="2026-01-01",
        end_date="2026-05-08",
        horizons=[5, 10, 20, 60],
        primary_horizon=5,
        calc_version="v1",
        score_version="manual_v1",
        quantiles=5,
        top_n=30,
    )

    assert list(result["factor_name"]) == ["ret_20", "qlib_ret_5"]
    assert list(result["status"]) == ["approved", "approved"]
    assert [kind for kind, _ in calls] == ["run", "approval", "run", "approval"]


def test_run_factor_gate_batch_preserves_explicit_empty_factor_names(monkeypatch):
    calls = []

    monkeypatch.setattr(
        factor_eval_batch,
        "candidate_factor_names",
        lambda: calls.append("candidate_factor_names") or ["ret_20"],
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: calls.append("load_multi_horizon_factor_eval_inputs"),
    )

    result = factor_eval_batch.run_factor_gate_batch(
        factor_names=[],
        start_date="2026-01-01",
        end_date="2026-05-08",
        horizons=[5, 10, 20, 60],
        primary_horizon=5,
        calc_version="v1",
        score_version="manual_v1",
        quantiles=5,
        top_n=30,
    )

    assert result.empty
    assert calls == []


def test_run_factor_gate_batch_rejects_missing_factor_data(monkeypatch):
    calls = []

    monkeypatch.setattr(
        factor_eval_batch,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame(columns=["trade_date", "asset_id", "factor_value"]),
            pd.DataFrame(
                {
                    "trade_date": ["2026-01-01"],
                    "asset_id": ["A"],
                    "forward_return_5d": [0.02],
                }
            ),
        ),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "generate_multi_horizon_report",
        lambda **kwargs: calls.append(("report", kwargs)),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "store_factor_eval_run",
        lambda **kwargs: calls.append(("run", kwargs)),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "store_factor_approval",
        lambda **kwargs: calls.append(("approval", kwargs)),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "_new_run_id",
        lambda factor_name: f"run-{factor_name}",
    )

    result = factor_eval_batch.run_factor_gate_batch(
        factor_names=["amount_vs_20d"],
        start_date="2026-01-01",
        end_date="2026-05-08",
        horizons=[5, 10, 20, 60],
        primary_horizon=5,
        calc_version="v1",
        score_version="manual_v1",
        quantiles=5,
        top_n=30,
    )

    assert list(result["factor_name"]) == ["amount_vs_20d"]
    assert list(result["status"]) == ["rejected"]
    assert list(result["reason"]) == ["missing_factor_data"]
    assert calls == [
        (
            "run",
            {
                "run_id": "run-amount_vs_20d",
                "factor_name": "amount_vs_20d",
                "calc_version": "v1",
                "start_date": "2026-01-01",
                "end_date": "2026-05-08",
                "horizons": [5, 10, 20, 60],
                "primary_horizon": 5,
                "status": "rejected",
                "reason": "missing_factor_data",
                "metrics": {
                    "decision": {
                        "factor_name": "amount_vs_20d",
                        "status": "rejected",
                        "reason": "missing_factor_data",
                        "primary_horizon": 5,
                    },
                    "multi_horizon": None,
                },
            },
        ),
        (
            "approval",
            {
                "factor_name": "amount_vs_20d",
                "calc_version": "v1",
                "score_version": "manual_v1",
                "status": "rejected",
                "reason": "missing_factor_data",
                "eval_run_id": "run-amount_vs_20d",
            },
        ),
    ]


def test_run_factor_gate_batch_can_use_walk_forward_validation(monkeypatch):
    calls = []

    def fake_load_multi_horizon_factor_eval_inputs(**kwargs):
        calls.append(("load", kwargs))
        return (
            pd.DataFrame(
                {
                    "trade_date": [kwargs["start_date"]],
                    "asset_id": ["A"],
                    "factor_value": [1.0],
                }
            ),
            pd.DataFrame(
                {
                    "trade_date": [kwargs["start_date"]],
                    "asset_id": ["A"],
                    "forward_return_5d": [0.02],
                }
            ),
        )

    def fake_generate_multi_horizon_report(**kwargs):
        start_date = kwargs["factors"].iloc[0]["trade_date"]
        if start_date == "2026-01-01":
            return {
                "factor_name": kwargs["factor_name"],
                "horizons": kwargs["horizons"],
                "reports": {
                    5: {"ic_summary": {"mean_ic": 0.05, "icir": 0.7, "ic_count": 30}}
                },
            }
        return {
            "factor_name": kwargs["factor_name"],
            "horizons": kwargs["horizons"],
            "reports": {
                5: {"ic_summary": {"mean_ic": 0.03, "icir": 0.5, "ic_count": 25}}
            },
        }

    monkeypatch.setattr(
        factor_eval_batch,
        "load_multi_horizon_factor_eval_inputs",
        fake_load_multi_horizon_factor_eval_inputs,
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "generate_multi_horizon_report",
        fake_generate_multi_horizon_report,
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "store_factor_eval_run",
        lambda **kwargs: calls.append(("run", kwargs)),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "store_factor_approval",
        lambda **kwargs: calls.append(("approval", kwargs)),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "_new_run_id",
        lambda factor_name: f"run-{factor_name}",
    )

    result = factor_eval_batch.run_factor_gate_batch(
        factor_names=["ret_20"],
        start_date="2026-01-01",
        end_date="2026-05-08",
        horizons=[5, 10, 20, 60],
        primary_horizon=5,
        calc_version="v1",
        score_version="manual_v1",
        quantiles=5,
        top_n=30,
        validation_start_date="2026-03-01",
    )

    assert list(result["factor_name"]) == ["ret_20"]
    assert result.iloc[0]["validation_mean_ic"] == 0.03
    assert result.iloc[0]["validation_ic_count"] == 25
    assert [kind for kind, _ in calls] == ["load", "load", "run", "approval"]
    assert calls[0][1]["start_date"] == "2026-01-01"
    assert calls[0][1]["end_date"] == "2026-02-28"
    assert calls[1][1]["start_date"] == "2026-03-01"
    assert calls[1][1]["end_date"] == "2026-05-08"
    assert calls[2][1]["metrics"]["walk_forward"]["validation_window"] == {
        "start_date": "2026-03-01",
        "end_date": "2026-05-08",
    }


def test_run_factor_gate_batch_writes_run_card_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        factor_eval_batch,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.02]}),
        ),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "generate_multi_horizon_report",
        lambda **kwargs: {
            "factor_name": kwargs["factor_name"],
            "horizons": kwargs["horizons"],
            "reports": {
                5: {
                    "ic_summary": {
                        "mean_ic": 0.04,
                        "icir": 0.6,
                        "ic_count": 30,
                    }
                }
            },
        },
    )
    monkeypatch.setattr(factor_eval_batch, "store_factor_eval_run", lambda **kwargs: None)
    monkeypatch.setattr(factor_eval_batch, "store_factor_approval", lambda **kwargs: None)
    monkeypatch.setattr(
        factor_eval_batch,
        "_new_run_id",
        lambda factor_name: f"run-{factor_name}",
    )

    result = factor_eval_batch.run_factor_gate_batch(
        factor_names=["ret_20"],
        start_date="2026-01-01",
        end_date="2026-05-08",
        horizons=[5, 10],
        output_dir=tmp_path,
    )

    assert Path(result.iloc[0]["run_card_json_path"]).exists()
    assert Path(result.iloc[0]["run_card_markdown_path"]).exists()
    assert Path(result.iloc[0]["metrics_json_path"]).exists()
    assert Path(result.iloc[0]["config_snapshot_path"]).exists()
    assert Path(result.iloc[0]["warnings_md_path"]).exists()
    assert Path(result.iloc[0]["data_coverage_json_path"]).exists()
    assert result.iloc[0]["run_card_json_path"].endswith("run_card.json")
    coverage = json.loads(Path(result.iloc[0]["data_coverage_json_path"]).read_text(encoding="utf-8"))
    assert coverage["coverage_ratio"] is None
    assert coverage["missing_dates"] is None
    assert coverage["missing_assets"] is None


@pytest.mark.parametrize("validation_start_date", ["2026-01-01", "2026-06-01"])
def test_run_factor_gate_batch_rejects_invalid_walk_forward_window(
    validation_start_date,
):
    with pytest.raises(ValueError, match="validation_start_date"):
        factor_eval_batch.run_factor_gate_batch(
            factor_names=[],
            start_date="2026-01-01",
            end_date="2026-05-08",
            horizons=[5, 10, 20, 60],
            validation_start_date=validation_start_date,
        )
