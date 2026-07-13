#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from stock_research.data_to_brief_enriched_report_docling_integration import (
    OUTPUT_DIR,
    POC_DIR,
    QUALITY_DIR,
    run_data_to_brief_enriched_report_docling_integration,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Data-to-Brief enriched report Docling integration pilot.")
    parser.add_argument("--poc-dir", default=str(POC_DIR))
    parser.add_argument("--quality-dir", default=str(QUALITY_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_data_to_brief_enriched_report_docling_integration(
        poc_dir=Path(args.poc_dir),
        quality_dir=Path(args.quality_dir),
        output_dir=Path(args.output_dir),
    )
    summary = result["summary"]
    output = Path(args.output_dir)
    print(f"data_to_brief_enriched_report_docling_integration|summary|{output / 'docling_integration_summary.json'}")
    print(f"data_to_brief_enriched_report_docling_integration|pilot_stock_count|{summary['pilot_stock_count']}")
    print(f"data_to_brief_enriched_report_docling_integration|parsed_stock_count|{summary['parsed_stock_count']}")
    print(f"data_to_brief_enriched_report_docling_integration|missing_pdf_evidence_required_count|{summary['missing_pdf_evidence_required_count']}")
    print(f"data_to_brief_enriched_report_docling_integration|acceptance_decision|{summary['acceptance_decision']}")


if __name__ == "__main__":
    main()
