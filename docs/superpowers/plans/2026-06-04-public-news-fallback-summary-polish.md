# Public News Fallback Summary Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve public-news TopN enrichment readability by generating usable low/medium-attention summaries and preserving candidate Chinese names in TopN-source metadata.

**Architecture:** Keep the source/feature/enrichment/dossier pipeline unchanged. Tighten two narrow seams only: enrich `topn_news_enrichment` with deterministic fallback summaries derived from counts/attention, and normalize `matched_candidates.stock_name` during TopN source backfill so later artifacts render human-readable names.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Improve TopN News Enrichment Summaries

**Files:**
- Modify: `src/stock_research/topn_news_enrichment.py`
- Test: `tests/test_topn_news_enrichment.py`

- [ ] Add failing tests covering non-empty fallback summaries for `low`/`medium` attention rows with zero keyword hits.
- [ ] Run `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_topn_news_enrichment.py -q` and confirm the new tests fail for the expected reason.
- [ ] Implement minimal deterministic wording so matched feature rows can emit readable consensus/catalyst summaries from counts and attention even without keyword triggers.
- [ ] Re-run `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_topn_news_enrichment.py -q` and confirm green.

### Task 2: Normalize Matched Candidate Display Names

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Test: `tests/test_public_news_fallback_adapter.py`

- [ ] Add failing tests showing TopN source backfill should keep Chinese `stock_name` when available and fall back from code-like placeholders to a cleaner value.
- [ ] Run `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_public_news_fallback_adapter.py -q` and confirm the new tests fail for the expected reason.
- [ ] Implement minimal normalization in candidate context building so `matched_candidates.stock_name` prefers a human-readable Chinese name when present.
- [ ] Re-run `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_public_news_fallback_adapter.py -q` and confirm green.

### Task 3: End-to-End Verification

**Files:**
- Inspect: `outputs/research/public_news_fallback_20260602/...`

- [ ] Run `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_news_source_backfill.py tests/test_news_features.py tests/test_topn_news_enrichment.py tests/test_mid_trend_position_dossier.py tests/test_public_news_fallback_adapter.py -q` and confirm the combined suite passes.
- [ ] Inspect refreshed enrichment and dossier artifacts to confirm summary text and candidate naming are improved for the real `2026-06-02` fallback run.
