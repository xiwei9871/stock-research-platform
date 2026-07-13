#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from stock_research.data_to_brief_docling_metadata_recovery import (
    INTEGRATION_DIR,
    OUTPUT_DIR,
    POC_DIR,
    run_data_to_brief_docling_metadata_recovery,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Data-to-Brief Docling page/table metadata recovery.")
    parser.add_argument("--poc-dir", default=str(POC_DIR))
    parser.add_argument("--integration-dir", default=str(INTEGRATION_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_data_to_brief_docling_metadata_recovery(
        poc_dir=Path(args.poc_dir),
        integration_dir=Path(args.integration_dir),
        output_dir=Path(args.output_dir),
    )
    summary = result["summary"]
    output = Path(args.output_dir)
    print(f"data_to_brief_docling_metadata_recovery|summary|{output / 'docling_metadata_recovery_summary.json'}")
    print(f"data_to_brief_docling_metadata_recovery|previous_citation_count|{summary['previous_citation_count']}")
    print(f"data_to_brief_docling_metadata_recovery|page_level_citation_count|{summary['page_level_citation_count']}")
    print(f"data_to_brief_docling_metadata_recovery|acceptance_decision|{summary['acceptance_decision']}")


if __name__ == "__main__":
    main()
