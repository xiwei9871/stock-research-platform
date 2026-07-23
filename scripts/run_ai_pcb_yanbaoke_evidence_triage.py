#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_research.ai_pcb_yanbaoke_evidence_triage import run_triage


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the offline, read-only AI PCB triage for the frozen Yanbaoke batch."
    )
    parser.add_argument(
        "--run-dir",
        default="outputs/research/theme_company_yanbaoke_20260723",
    )
    parser.add_argument("--expected-queue-rows", type=int, default=474)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    result = run_triage(
        input_dir=run_dir,
        output_dir=run_dir,
        expected_queue_rows=args.expected_queue_rows,
    )
    print(
        json.dumps(
            {
                "queue_rows_considered": result.queue_rows_considered,
                "selected_source_records": result.selected_source_records,
                "selected_content_identities": result.selected_content_identities,
                "duplicate_source_records": result.duplicate_source_records,
                "output_paths": [str(path) for path in result.output_paths],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
