#!/usr/bin/env python3
from __future__ import annotations

from stock_research.data_to_brief_docling_90_stock_pdf_acquisition import (
    run_data_to_brief_docling_90_stock_pdf_acquisition,
)


def main() -> None:
    result = run_data_to_brief_docling_90_stock_pdf_acquisition()
    summary = result["summary"]
    print(f"data_to_brief_docling_90_stock_pdf_acquisition_v1|missing_pdf_input_count|{summary['missing_pdf_input_count']}")
    print(f"data_to_brief_docling_90_stock_pdf_acquisition_v1|downloaded_pdf_count|{summary['downloaded_pdf_count']}")
    print(f"data_to_brief_docling_90_stock_pdf_acquisition_v1|downloaded_stock_count|{summary['downloaded_stock_count']}")
    print(f"data_to_brief_docling_90_stock_pdf_acquisition_v1|download_dir|{summary['download_dir']}")


if __name__ == "__main__":
    main()
