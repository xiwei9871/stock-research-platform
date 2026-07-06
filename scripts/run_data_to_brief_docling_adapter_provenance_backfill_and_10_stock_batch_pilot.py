#!/usr/bin/env python3
from __future__ import annotations

from stock_research.data_to_brief_docling_adapter_provenance_backfill_batch import (
    run_docling_adapter_provenance_backfill_10_stock_batch,
)


def main() -> None:
    result = run_docling_adapter_provenance_backfill_10_stock_batch()
    summary = result["summary"]
    print(
        "data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1|"
        f"acceptance_decision|{summary['acceptance_decision']}"
    )
    print(
        "data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1|"
        f"pilot_stock_count|{summary['pilot_stock_count']}"
    )
    print(
        "data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1|"
        f"page_level_citation_count|{summary['page_level_citation_count']}"
    )


if __name__ == "__main__":
    main()
