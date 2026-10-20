from pathlib import Path

from stock_research import schema


def test_schema_declares_tdx_auction_staging_and_accepts_tdx_source():
    ddl = schema.CREATE_TABLES_SQL + schema.CREATE_RESEARCH_EXTENSION_SQL

    assert "staging.tdx_stock_auction_bar" in ddl
    assert "source_endpoint" in ddl
    assert "order_count" in ddl
    assert "volume_unit" in ddl
    assert "source IN ('tushare', 'tdx')" in ddl


def test_project_declares_pinned_eltdx_dependency():
    pyproject = Path(__file__).parents[1].joinpath("pyproject.toml").read_text()

    assert '"eltdx==3.1.3"' in pyproject
