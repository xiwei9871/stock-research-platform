from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_research.tech_bottleneck_review_universe_operator_smoke import run_audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit tech bottleneck review-universe manual decision overlay.")
    parser.add_argument(
        "--output-dir",
        default="outputs/research/tech_bottleneck_review_universe_operator_smoke_and_audit_v1/audit",
    )
    args = parser.parse_args()
    result = run_audit(output_dir=Path(args.output_dir))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
