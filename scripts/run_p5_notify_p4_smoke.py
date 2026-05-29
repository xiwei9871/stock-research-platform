#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from stock_research.p5.notifications import (
    write_p4_smoke_feishu_preview,
    write_p4_smoke_notification_artifacts,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-log", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-command", default="")
    parser.add_argument("--feishu-preview", action="store_true")
    parser.add_argument("--feishu-output-dir")
    args = parser.parse_args(argv)

    smoke_log = Path(args.smoke_log)
    smoke_lines = [
        line
        for line in smoke_log.read_text(encoding="utf-8").splitlines()
        if line.startswith("p4_read_model_smoke")
    ]
    notification_result = write_p4_smoke_notification_artifacts(
        smoke_lines,
        output_dir=args.output_dir,
        source_command=args.source_command,
        source_log_path=str(smoke_log),
    )
    print(
        "p5_p4_smoke_notification|"
        f"status|{notification_result['status']}|"
        f"trade_date|{notification_result['trade_date']}|"
        f"severity|{notification_result['severity']}|"
        f"preview|{notification_result['preview_path']}|"
        f"delivery_log|{notification_result['delivery_log_path']}"
    )

    if args.feishu_preview:
        feishu_output_dir = args.feishu_output_dir or str(Path(args.output_dir) / "feishu")
        feishu_result = write_p4_smoke_feishu_preview(
            notification_result["preview_path"],
            output_dir=feishu_output_dir,
        )
        print(
            "p5_p4_smoke_feishu_preview|"
            f"status|{feishu_result['status']}|"
            f"trade_date|{feishu_result['trade_date']}|"
            f"items|{feishu_result['item_count']}|"
            f"preview|{feishu_result['preview_path']}|"
            f"delivery_log|{feishu_result['delivery_log_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
