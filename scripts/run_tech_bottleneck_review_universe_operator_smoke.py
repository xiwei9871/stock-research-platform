from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_research.tech_bottleneck_review_universe_operator_smoke import run_smoke


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tech bottleneck review-universe operator smoke checks.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-test-decision", action="store_true")
    parser.add_argument("--stock-code", default="")
    parser.add_argument("--decision", default="need_more_evidence")
    parser.add_argument("--comment", default="")
    parser.add_argument("--evidence-checked", action="store_true")
    parser.add_argument("--write-token", default="")
    parser.add_argument(
        "--output-dir",
        default="outputs/research/tech_bottleneck_review_universe_operator_smoke_and_audit_v1/dry_run",
    )
    args = parser.parse_args()
    result = run_smoke(
        dry_run=args.dry_run or not args.write_test_decision,
        write_test_decision=args.write_test_decision,
        stock_code=args.stock_code,
        decision=args.decision,
        comment=args.comment,
        evidence_checked=args.evidence_checked,
        write_token=args.write_token,
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
