from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_research.dashboard import tech_bottleneck_review_decisions as decisions


def main() -> None:
    parser = argparse.ArgumentParser(description="Export tech bottleneck review-universe manual decision overlay.")
    parser.add_argument("--output-dir", default=str(decisions.OVERLAY_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    decisions.OVERLAY_DIR = output_dir
    decisions.load_ledger.cache_clear()
    decisions.load_current_overlay.cache_clear()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / decisions.LEDGER_PATH_NAME).touch(exist_ok=True)

    overlay = decisions.load_current_overlay()
    summary = decisions.build_decision_summary()
    (output_dir / decisions.CURRENT_OVERLAY_NAME).write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / decisions.SUMMARY_JSON_NAME).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / decisions.SUMMARY_MD_NAME).write_text(decisions._summary_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
