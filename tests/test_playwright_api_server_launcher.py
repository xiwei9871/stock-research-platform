from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_api_launcher_imports_stock_research_from_current_checkout() -> None:
    result = subprocess.run(
        ["node", "scripts/run-playwright-api-server.mjs", "--print-import-root"],
        cwd=ROOT / "dashboard",
        check=True,
        capture_output=True,
        text=True,
    )

    imported = Path(result.stdout.strip()).resolve()
    assert imported.is_relative_to((ROOT / "src").resolve())
