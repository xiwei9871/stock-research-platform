#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from stock_research.industry_chain_theme_research import list_selected_chain_research
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_research_priority import load_theme_research_priority_package


def build_five_theme_report(
    *,
    catalog: dict[str, Any] | None = None,
    theme_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_catalog = catalog if catalog is not None else load_industry_catalog()
    resolved_context = (
        theme_context
        if theme_context is not None
        else load_theme_research_priority_package()
    )
    rows = list_selected_chain_research(
        catalog=resolved_catalog,
        theme_context=resolved_context,
    )
    reviewed_count = sum(row["research_status"] == "reviewed" for row in rows)
    researching_count = sum(row["research_status"] == "researching" for row in rows)
    catalog_link_count = sum(row["coverage"]["checks"]["catalog_link"] for row in rows)
    all_ready = len(rows) == 5 and all(row["coverage"]["ready"] for row in rows)
    return {
        "selected_theme_count": len(rows),
        "catalog_link_count": catalog_link_count,
        "reviewed_theme_count": reviewed_count,
        "researching_theme_count": researching_count,
        "theme_results": rows,
        "all_required_sections_ready": all_ready,
        "completion_status": "ready" if all_ready else "not_ready",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    report = build_five_theme_report()
    if args.format == "markdown":
        print(f"# Five-theme completion: {report['completion_status']}")
        print()
        for row in report["theme_results"]:
            print(
                f"- {row['chain_name']}: {row['research_status']} "
                f"({row['source_count']} sources, {row['claim_count']} claims, "
                f"{row['reviewed_company_count']} reviewed companies)"
            )
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["completion_status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
