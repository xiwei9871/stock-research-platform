import pandas as pd

from stock_research.factor_eval_batch_cli import build_parser, main


def test_factor_eval_batch_cli_parser_accepts_arguments():
    args = build_parser().parse_args(
        [
            "--factor-names",
            "alpha101_delta_close_1_rank,gtja191_amount_momentum_5_10",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
            "--horizons",
            "5,10,20,60",
            "--primary-horizon",
            "5",
            "--calc-version",
            "v1",
            "--score-version",
            "manual_v1",
            "--quantiles",
            "5",
            "--top-n",
            "30",
        ]
    )

    assert args.factor_names == "alpha101_delta_close_1_rank,gtja191_amount_momentum_5_10"
    assert args.horizons == "5,10,20,60"
    assert args.primary_horizon == 5


def test_factor_eval_batch_cli_main_prints_stable_rows(monkeypatch, capsys):
    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "factor_name": "alpha101_delta_close_1_rank",
                    "status": "approved",
                    "reason": "passed_thresholds",
                    "primary_horizon": 5,
                    "eval_run_id": "run-1",
                }
            ]
        )

    monkeypatch.setattr(
        "sys.argv",
        [
            "python -m stock_research.factor_eval_batch_cli",
            "--factor-names",
            "alpha101_delta_close_1_rank",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ],
    )

    main(runner=fake_runner)

    assert calls[0]["factor_names"] == ["alpha101_delta_close_1_rank"]
    assert calls[0]["horizons"] == [5, 10, 20, 60]
    assert capsys.readouterr().out.strip() == (
        "factor_gate_batch|alpha101_delta_close_1_rank|approved|passed_thresholds|5|run-1"
    )
