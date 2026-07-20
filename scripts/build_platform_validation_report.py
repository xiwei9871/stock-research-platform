#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_research.platform_validation_report import build_platform_validation_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic platform-validation audit artifacts from Playwright JSON."
    )
    parser.add_argument("inventory", type=Path, help="Canonical platform route inventory JSON")
    parser.add_argument(
        "--playwright-results",
        type=Path,
        action="append",
        required=True,
        help="Playwright JSON reporter output; repeat for each profile/project result",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Audit artifact directory")
    parser.add_argument("--audit-id", required=True, help="Stable identifier for this audit run")
    parser.add_argument("--revision", required=True, help="Source revision audited")
    parser.add_argument("--audit-date", required=True, help="Audit date, normally YYYY-MM-DD")
    parser.add_argument(
        "--baseline-status",
        choices=("baseline_candidate", "trusted_baseline"),
        default="baseline_candidate",
        help="Requested baseline state; trusted_baseline is validated fail-closed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = build_platform_validation_report(
        inventory=args.inventory,
        playwright_result_paths=args.playwright_results,
        output_dir=args.output_dir,
        audit_id=args.audit_id,
        revision=args.revision,
        audit_date=args.audit_date,
        baseline_status=args.baseline_status,
    )
    print(json.dumps({name: str(path) for name, path in sorted(paths.items())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
