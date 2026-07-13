#!/usr/bin/env python3
from __future__ import annotations

from stock_research.data_to_brief_docling_90_stock_batch_precheck import (
    run_data_to_brief_docling_90_stock_batch_precheck,
)


def main() -> None:
    result = run_data_to_brief_docling_90_stock_batch_precheck()
    summary = result["summary"]
    print(f"data_to_brief_docling_90_stock_batch_precheck_v1|acceptance_decision|{summary['acceptance_decision']}")
    print(f"data_to_brief_docling_90_stock_batch_precheck_v1|stock_count|{summary['stock_count']}")
    print(f"data_to_brief_docling_90_stock_batch_precheck_v1|local_pdf_stock_count|{summary['local_pdf_stock_count']}")
    print(f"data_to_brief_docling_90_stock_batch_precheck_v1|cached_parser_artifact_count|{summary['cached_parser_artifact_count']}")


if __name__ == "__main__":
    main()
