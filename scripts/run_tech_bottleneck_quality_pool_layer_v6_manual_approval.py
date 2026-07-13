from __future__ import annotations

from stock_research.tech_bottleneck_quality_pool_layer_v6_manual_approval import run


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
