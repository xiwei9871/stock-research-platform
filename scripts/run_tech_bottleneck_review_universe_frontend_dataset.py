import os

from stock_research.tech_bottleneck_review_universe_frontend_dataset import run


def _publish_enabled() -> bool:
    return os.environ.get("STOCK_RESEARCH_PUBLISH_DB", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run(publish_db=_publish_enabled()), ensure_ascii=False, indent=2, sort_keys=True))
