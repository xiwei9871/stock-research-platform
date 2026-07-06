#!/usr/bin/env python3
from __future__ import annotations

from stock_research.data_to_brief_docling_90_stock_full_cold_parse_batch import (
    run_data_to_brief_docling_90_stock_full_cold_parse_batch,
)


def main() -> None:
    result = run_data_to_brief_docling_90_stock_full_cold_parse_batch()
    summary = result["summary"]
    print(f"data_to_brief_docling_90_stock_full_cold_parse_batch_v1|acceptance_decision|{summary['acceptance_decision']}")
    print(f"data_to_brief_docling_90_stock_full_cold_parse_batch_v1|stock_count|{summary['stock_count']}")
    print(f"data_to_brief_docling_90_stock_full_cold_parse_batch_v1|cached_parser_artifact_reused_count|{summary['cached_parser_artifact_reused_count']}")
    print(f"data_to_brief_docling_90_stock_full_cold_parse_batch_v1|cold_parse_required_count|{summary['cold_parse_required_count']}")
    print(f"data_to_brief_docling_90_stock_full_cold_parse_batch_v1|parser_artifact_ready_count|{summary['parser_artifact_ready_count']}")


if __name__ == "__main__":
    main()
