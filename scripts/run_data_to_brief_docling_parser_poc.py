#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from stock_research.data_to_brief_docling_parser_poc import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SOURCE_ROOTS,
    run_data_to_brief_docling_parser_poc,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Data-to-Brief Docling parser PoC.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--source-root",
        action="append",
        dest="source_roots",
        default=None,
        help="Local root to scan for pilot-stock PDFs. May be passed multiple times.",
    )
    parser.add_argument("--limit-per-stock", type=int, default=1)
    parser.add_argument("--skip-docling", action="store_true", help="Only write discovery/pypdf outputs; skip Docling conversion.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_roots = [Path(root) for root in args.source_roots] if args.source_roots else DEFAULT_SOURCE_ROOTS
    result = run_data_to_brief_docling_parser_poc(
        output_dir=args.output_dir,
        source_roots=source_roots,
        limit_per_stock=args.limit_per_stock,
        skip_docling=args.skip_docling,
    )
    summary = result["summary"]
    paths = summary["paths"]
    print(f"data_to_brief_docling_parser_poc|summary|{Path(args.output_dir) / 'pilot_run_summary.json'}")
    print(f"data_to_brief_docling_parser_poc|parser_comparison_matrix|{paths['parser_comparison_matrix']}")
    print(f"data_to_brief_docling_parser_poc|source_chunk_manifest|{paths['source_chunk_manifest']}")
    print(f"data_to_brief_docling_parser_poc|pilot_evidence_matrix|{paths['pilot_evidence_matrix']}")
    print(f"data_to_brief_docling_parser_poc|local_pdf_count|{summary['local_pdf_count']}")
    print(f"data_to_brief_docling_parser_poc|docling_parsed_count|{summary['docling_parsed_count']}")
    print(f"data_to_brief_docling_parser_poc|evidence_required_stock_count|{summary['evidence_required_stock_count']}")


if __name__ == "__main__":
    main()
