import argparse

from stock_research.factor_eval_batch import run_factor_gate_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stock_research.factor_eval_batch_cli")
    parser.add_argument("--factor-names", type=parse_factor_names)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--horizons", default="5,10,20,60")
    parser.add_argument("--primary-horizon", type=int, default=5)
    parser.add_argument("--calc-version", default="v1")
    parser.add_argument("--score-version", default="manual_v1")
    parser.add_argument("--quantiles", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=30)
    return parser


def main(runner=run_factor_gate_batch) -> None:
    args = build_parser().parse_args()
    result = runner(
        factor_names=args.factor_names,
        start_date=args.start_date,
        end_date=args.end_date,
        horizons=[int(value) for value in _parse_csv(args.horizons)],
        primary_horizon=args.primary_horizon,
        calc_version=args.calc_version,
        score_version=args.score_version,
        quantiles=args.quantiles,
        top_n=args.top_n,
    )
    for row in result.to_dict("records"):
        print(
            "factor_gate_batch|"
            f"{row['factor_name']}|{row['status']}|{row['reason']}|"
            f"{row['primary_horizon']}|{row['eval_run_id']}"
        )


def parse_factor_names(value: str) -> list[str]:
    parts = _parse_csv(value)
    if not parts or len(parts) != len(value.split(",")):
        raise argparse.ArgumentTypeError("--factor-names must not contain empty values")
    return parts


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    main()
