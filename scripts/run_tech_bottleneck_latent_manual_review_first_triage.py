from __future__ import annotations

import json

from stock_research.tech_bottleneck_latent_manual_review_first_triage import run


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
