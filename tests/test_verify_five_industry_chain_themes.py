from copy import deepcopy

from scripts.verify_five_industry_chain_themes import build_five_theme_report
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_research_priority import load_theme_research_priority_package


def test_five_theme_completion_report_is_ready():
    report = build_five_theme_report()

    assert report["selected_theme_count"] == 5
    assert report["catalog_link_count"] == 5
    assert report["reviewed_theme_count"] == 5
    assert report["researching_theme_count"] == 0
    assert report["all_required_sections_ready"] is True
    assert report["completion_status"] == "ready"
    assert all(row["coverage"]["ready"] for row in report["theme_results"])


def test_five_theme_completion_report_fails_when_a_source_gate_breaks():
    context = deepcopy(load_theme_research_priority_package())
    context["theme_package"]["sources"] = [
        row
        for row in context["theme_package"]["sources"]
        if not row["source_id"].startswith("storage_")
    ]

    report = build_five_theme_report(
        catalog=load_industry_catalog(),
        theme_context=context,
    )

    storage = next(
        row for row in report["theme_results"] if row["chain_id"] == "new_energy_storage"
    )
    assert storage["coverage"]["checks"]["accepted_source_count"] is False
    assert report["completion_status"] == "not_ready"
