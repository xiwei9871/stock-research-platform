from stock_research.tech_bottleneck_review_universe_evidence_completion_audit import run


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
