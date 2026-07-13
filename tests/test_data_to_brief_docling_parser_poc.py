from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd

from stock_research.data_to_brief_docling_parser_poc import (
    DEFAULT_PILOT_STOCKS,
    run_data_to_brief_docling_parser_poc,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_parser_poc.py"


def test_docling_parser_poc_writes_evidence_ready_outputs(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    output_dir = tmp_path / "outputs"
    source_root.mkdir()
    pdf_path = source_root / "20260506-交银国际证券-中微公司-688012.SH-产品进一步取得进展.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    def fake_docling_parser(path: Path) -> dict[str, object]:
        assert path == pdf_path
        return {
            "status": "parsed",
            "parser": "docling",
            "markdown": "# 中微公司\n\n公司刻蚀设备产品进一步取得进展。\n\n| 项目 | 内容 |\n| --- | --- |\n| 产品 | 刻蚀设备 |",
            "json": {
                "pages": {"1": {"page_no": 1}},
                "texts": [
                    {
                        "self_ref": "#/texts/0",
                        "label": "section_header",
                        "text": "中微公司",
                        "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
                    },
                    {
                        "self_ref": "#/texts/1",
                        "label": "text",
                        "text": "公司刻蚀设备产品进一步取得进展。",
                        "prov": [{"page_no": 1, "bbox": {"l": 5, "t": 6, "r": 7, "b": 8}}],
                    },
                ],
                "tables": [
                    {
                        "self_ref": "#/tables/0",
                        "prov": [{"page_no": 1, "bbox": {"l": 9, "t": 10, "r": 11, "b": 12}}],
                        "data": {"grid": [[{"text": "项目"}, {"text": "内容"}], [{"text": "产品"}, {"text": "刻蚀设备"}]]},
                    }
                ],
            },
            "tables": [{"table_id": "T1", "row_count": 1, "column_count": 2, "caption": "产品表"}],
            "error_type": "",
            "error_message": "",
        }

    result = run_data_to_brief_docling_parser_poc(
        output_dir=output_dir,
        source_roots=[source_root],
        limit_per_stock=1,
        docling_parser=fake_docling_parser,
    )

    required = {
        "docling_install_smoke.json",
        "parser_comparison_matrix.csv",
        "table_inventory.csv",
        "source_chunk_manifest.csv",
        "pilot_evidence_matrix.csv",
        "pilot_claim_citation_map.csv",
        "pilot_run_summary.json",
    }
    assert required.issubset({path.name for path in output_dir.iterdir()})
    assert (output_dir / "parsed_documents" / "688012_中微公司_1.md").exists()
    assert (output_dir / "parsed_documents" / "688012_中微公司_1.json").exists()
    assert (output_dir / "chunks" / "688012_中微公司_chunks.csv").exists()

    summary = json.loads((output_dir / "pilot_run_summary.json").read_text(encoding="utf-8"))
    assert summary["pilot_stock_count"] == len(DEFAULT_PILOT_STOCKS)
    assert summary["local_pdf_count"] == 1
    assert summary["docling_parsed_count"] == 1
    assert summary["evidence_required_stock_count"] == len(DEFAULT_PILOT_STOCKS) - 1
    assert result["summary"]["output_dir"] == str(output_dir)

    evidence = pd.read_csv(output_dir / "pilot_evidence_matrix.csv", dtype={"stock_code": str})
    claim_map = pd.read_csv(output_dir / "pilot_claim_citation_map.csv", dtype={"stock_code": str})
    sources = pd.read_csv(output_dir / "source_chunk_manifest.csv", dtype={"stock_code": str})
    tables = pd.read_csv(output_dir / "table_inventory.csv", dtype={"stock_code": str})
    comparison = pd.read_csv(output_dir / "parser_comparison_matrix.csv", dtype={"stock_code": str})

    parsed_rows = evidence[evidence["stock_code"].eq("688012")]
    assert not parsed_rows.empty
    assert parsed_rows["citation_id"].notna().all()
    assert set(parsed_rows["citation_id"]).issubset(set(sources["citation_id"]))
    assert claim_map["citation_id"].notna().all()
    assert evidence["evidence_required"].isin([True, False]).all()
    assert evidence[evidence["stock_code"].eq("002371")]["evidence_required"].all()
    assert tables.iloc[0]["table_id"] == "T1"
    assert {"page_start", "page_end", "page_locator", "bbox", "docling_item_ref", "section_heading", "citation_granularity", "citation_ready"}.issubset(sources.columns)
    assert sources[sources["stock_code"].eq("688012")]["citation_granularity"].eq("page_level").all()
    assert sources[sources["stock_code"].eq("688012")]["page_locator"].fillna("").astype(str).str.len().gt(0).all()
    assert {"page_locator", "bbox", "docling_table_ref", "table_title", "table_markdown", "table_csv_preview", "table_html_preview", "table_relevance", "citation_granularity"}.issubset(tables.columns)
    assert tables.iloc[0]["citation_granularity"] == "page_level"
    assert str(tables.iloc[0]["page_locator"]) == "1"
    parsed_comparison = comparison[comparison["stock_code"].eq("688012")]
    assert parsed_comparison.iloc[0]["docling_status"] == "parsed"


def test_docling_parser_poc_script_prints_summary_paths(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    output_dir = tmp_path / "outputs"
    source_root.mkdir()

    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv/bin/python"),
            str(SCRIPT),
            "--output-dir",
            str(output_dir),
            "--source-root",
            str(source_root),
            "--limit-per-stock",
            "1",
            "--skip-docling",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "data_to_brief_docling_parser_poc|summary|" in result.stdout
    assert "data_to_brief_docling_parser_poc|parser_comparison_matrix|" in result.stdout
    assert (output_dir / "pilot_run_summary.json").exists()
