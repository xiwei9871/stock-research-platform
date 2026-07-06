#!/usr/bin/env python3
from __future__ import annotations

from stock_research.data_to_brief_docling_30_stock_batch_pilot import (
    run_data_to_brief_docling_30_stock_batch_pilot,
)


def main() -> None:
    result = run_data_to_brief_docling_30_stock_batch_pilot()
    summary = result["summary"]
    print(f"data_to_brief_docling_30_stock_batch_pilot_v1|acceptance_decision|{summary['acceptance_decision']}")
    print(f"data_to_brief_docling_30_stock_batch_pilot_v1|stock_count|{summary['stock_count']}")
    print(f"data_to_brief_docling_30_stock_batch_pilot_v1|local_pdf_stock_count|{summary['local_pdf_stock_count']}")
    print(f"data_to_brief_docling_30_stock_batch_pilot_v1|page_level_citations|{summary['citations_with_page_locator_count']}")


if __name__ == "__main__":
    main()
