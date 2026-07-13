#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib import request


OLD_MOCK_VALUES = {3168.44, 9821.31, 1943.52, 772.18, 1088.67}


def fetch_json(url: str) -> dict[str, Any]:
    try:
        opener = request.build_opener(request.ProxyHandler({}))
        with opener.open(url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - release smoke should fail with a compact message.
        raise SystemExit(f"failed to fetch {url}: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _url(api_base: str, path: str) -> str:
    return f"{api_base.rstrip('/')}{path}"


def _check_no_old_mock_values(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False)
    for value in OLD_MOCK_VALUES:
        _require(str(value) not in rendered, "old mock market overview value detected")


def run_check(*, api_base: str, trade_date: str) -> dict[str, Any]:
    overview = fetch_json(_url(api_base, f"/market-monitor/overview?trade_date={trade_date}"))
    heatmap = fetch_json(
        _url(api_base, f"/market-monitor/sectors/heatmap?trade_date={trade_date}&type=industry")
    )
    fund_flow = fetch_json(
        _url(api_base, f"/market-monitor/sectors/fund-flow?trade_date={trade_date}&type=industry")
    )

    _require(overview.get("data_status") == "completed", "market overview is not completed")
    _require(not overview.get("warnings"), f"market overview warnings: {overview.get('warnings')}")
    _require(len(overview.get("indices") or []) >= 5, "market overview has fewer than 5 indices")
    _require(overview.get("total_amount") is not None, "market overview total_amount is missing")
    _require(overview.get("up_count") is not None, "market overview up_count is missing")
    _require(overview.get("down_count") is not None, "market overview down_count is missing")
    _require(overview.get("limit_up_count") is not None, "market overview limit_up_count is missing")
    _require(overview.get("limit_down_count") is not None, "market overview limit_down_count is missing")
    _check_no_old_mock_values(overview)

    _require(heatmap.get("data_status") == "completed", "industry heatmap is not completed")
    _require(len(heatmap.get("items") or []) > 0, "industry heatmap has no rows")

    _require(fund_flow.get("data_status") == "completed", "industry fund-flow is not completed")
    _require(
        len(fund_flow.get("inflow") or []) + len(fund_flow.get("outflow") or []) > 0,
        "industry fund-flow has no directional rows",
    )

    return {
        "status": "pass",
        "trade_date": trade_date,
        "overview": {"index_count": len(overview.get("indices") or [])},
        "heatmap": {"item_count": len(heatmap.get("items") or [])},
        "fund_flow": {
            "inflow_count": len(fund_flow.get("inflow") or []),
            "outflow_count": len(fund_flow.get("outflow") or []),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local read-only Market Monitor release smoke")
    parser.add_argument("--api-base", default="http://127.0.0.1:8765/api")
    parser.add_argument("--trade-date", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_check(api_base=args.api_base, trade_date=args.trade_date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
