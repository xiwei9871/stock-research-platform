import json
import importlib.util
from pathlib import Path
from urllib.error import HTTPError

import pytest


def _load_gate_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_market_monitor_local_release.py"
    spec = importlib.util.spec_from_file_location("check_market_monitor_local_release", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


gate = _load_gate_module()


def test_market_monitor_local_release_gate_passes_completed_payloads(monkeypatch):
    payloads = {
        "/api/market-monitor/overview?trade_date=2026-06-26": {
            "data_status": "completed",
            "warnings": [],
            "indices": [
                {"name": "上证指数", "close": 4027.26},
                {"name": "深证成指", "close": 15782.22},
                {"name": "创业板指", "close": 4194.21},
                {"name": "科创50", "close": 2032.28},
                {"name": "北证50", "close": 1266.90},
            ],
            "total_amount": 3532905581027.03,
            "up_count": 755,
            "down_count": 4393,
            "limit_up_count": 60,
            "limit_down_count": 38,
        },
        "/api/market-monitor/sectors/heatmap?trade_date=2026-06-26&type=industry": {
            "data_status": "completed",
            "items": [{"sector_name": "计算机、通信和其他电子设备制造业"}],
        },
        "/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=industry": {
            "data_status": "completed",
            "inflow": [{"sector_name": "铁路、船舶、航空航天和其他运输设备制造业"}],
            "outflow": [{"sector_name": "保险业"}],
        },
    }

    monkeypatch.setattr(
        gate,
        "fetch_json",
        lambda url: payloads[url.removeprefix("http://127.0.0.1:8765")],
    )

    result = gate.run_check(api_base="http://127.0.0.1:8765/api", trade_date="2026-06-26")

    assert result["status"] == "pass"
    assert result["overview"]["index_count"] == 5
    assert result["heatmap"]["item_count"] == 1
    assert result["fund_flow"]["inflow_count"] == 1


def test_market_monitor_local_release_gate_rejects_old_mock_overview(monkeypatch):
    def fake_fetch_json(url):
        if "overview" in url:
            return {
                "data_status": "completed",
                "warnings": [],
                "indices": [
                    {"name": "上证指数", "close": 3168.44},
                    {"name": "深证成指", "close": 15782.22},
                    {"name": "创业板指", "close": 4194.21},
                    {"name": "科创50", "close": 2032.28},
                    {"name": "北证50", "close": 1266.90},
                ],
                "total_amount": 1526000000000,
                "up_count": 3612,
                "down_count": 1491,
                "limit_up_count": 90,
                "limit_down_count": 10,
            }
        if "heatmap" in url:
            return {"data_status": "completed", "items": [{"sector_name": "行业"}]}
        return {"data_status": "completed", "inflow": [{"sector_name": "行业"}], "outflow": []}

    monkeypatch.setattr(gate, "fetch_json", fake_fetch_json)

    with pytest.raises(SystemExit, match="old mock market overview value detected"):
        gate.run_check(api_base="http://127.0.0.1:8765/api", trade_date="2026-06-26")


def test_fetch_json_reports_http_error(monkeypatch):
    class FailingOpener:
        def open(self, *_args, **_kwargs):
            raise HTTPError("http://local", 500, "boom", {}, None)

    monkeypatch.setattr(gate.request, "build_opener", lambda *_args, **_kwargs: FailingOpener())

    with pytest.raises(SystemExit, match="failed to fetch http://local"):
        gate.fetch_json("http://local")
