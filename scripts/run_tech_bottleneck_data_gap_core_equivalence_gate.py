from __future__ import annotations

import json

from stock_research.tech_bottleneck_data_gap_core_equivalence_gate import run


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
