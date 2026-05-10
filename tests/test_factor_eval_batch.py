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
