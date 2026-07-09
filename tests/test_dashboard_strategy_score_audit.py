import json

import pandas as pd

from stock_research.dashboard.strategy_score_audit import load_strategy_score_audit_payload


def test_score_audit_uses_synced_detail_file_when_summary_has_local_absolute_path(tmp_path):
    output_root = tmp_path / "outputs"
    output_dir = output_root / "research" / "strategy_daily_eod" / "2026-07-03"
    output_dir.mkdir(parents=True)
    detail_path = output_dir / "strategy_score_audit_detail.csv"
    pd.DataFrame(
        [
            {
                "trade_date": "2026-07-03",
                "strategy_id": "tech_bottleneck",
                "asset_id": "CN:SZ:000001",
                "anomaly_flags": "[]",
            }
        ]
    ).to_csv(detail_path, index=False)
    (output_dir / "strategy_score_audit_summary.json").write_text(
        json.dumps(
            {
                "trade_date": "2026-07-03",
                "status": "success",
                "total_rows": 1,
                "selected_rows": 1,
                "anomaly_row_count": 0,
                "strategies": [],
                "detail_path": "/mnt/internal/stock_research/outputs/research/strategy_daily_eod/2026-07-03/strategy_score_audit_detail.csv",
            }
        ),
        encoding="utf-8",
    )

    payload = load_strategy_score_audit_payload(trade_date="2026-07-03", output_root=output_root)

    assert payload["overall_status"] == "ok"
    assert payload["sample_rows"][0]["asset_id"] == "CN:SZ:000001"
