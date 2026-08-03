from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_theme_report_e2e_script_is_discoverable_and_default_e2e_excludes_it() -> None:
    package = json.loads((ROOT / "dashboard" / "package.json").read_text(encoding="utf-8"))
    config = (ROOT / "dashboard" / "playwright.config.ts").read_text(encoding="utf-8")

    assert package["scripts"]["test:e2e:theme-reports"] == "node scripts/run-theme-report-e2e.mjs"
    assert "testIgnore: themeReportRealE2E ? [] : ['**/theme-research-full-flow.spec.ts']" in config
