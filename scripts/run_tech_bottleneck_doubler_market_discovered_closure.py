from __future__ import annotations

import json

from stock_research.tech_bottleneck_doubler_market_discovered_closure import run


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
