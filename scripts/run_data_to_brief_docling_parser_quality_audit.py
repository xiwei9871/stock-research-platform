#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from stock_research.data_to_brief_docling_parser_quality_audit import (
    DEFAULT_OUTPUT_DIR,
    run_data_to_brief_docling_parser_quality_audit,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Data-to-Brief Docling parser quality audit.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_data_to_brief_docling_parser_quality_audit(output_dir=args.output_dir)
    output = Path(args.output_dir)
    summary = result["summary"]
    print(f"data_to_brief_docling_parser_quality_audit|summary|{output / 'docling_parser_quality_summary.json'}")
    print(f"data_to_brief_docling_parser_quality_audit|chunk_count|{summary['chunk_count']}")
    print(f"data_to_brief_docling_parser_quality_audit|table_count|{summary['table_count']}")


if __name__ == "__main__":
    main()
