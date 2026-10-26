# P2 Remote-Copy Audit — 2026-10-26 (read-only, no deletion)

Method: `du -sm` on local vs remote
(`stock-prod:/home/jqz/code/stock-research-platform-main/outputs/research/`).

| Directory | Local | Remote | Remote copy complete? |
|---|---|---|---|
| tech_bottleneck_expansion_queue_primary_source_backfill_v1 | 432 MB | 14 MB | NO — metadata/index only, raw PDF evidence local-only |
| tech_bottleneck_latent_manual_review_collection_batch1_v1 | 163 MB | 1 MB | NO |
| stock_report_library_100_20261019 | 305 MB | 305 MB | YES — size-identical mirror |
| theme_research_yanbaoke_quota_fill100_20261019 | 145 MB | ABSENT | NO |
| theme_research_yanbaoke_gap_pilot_20261019 | 66 MB | ABSENT | NO |

## Verdict

P2 deletion precondition ("reliable remote copy exists") is met by **1 of 5**
candidates (~305 MB of ~1.1 GB). Even that one requires a content-level
verification (file count + sha256 sample) before any removal — not done here.

**No deletion performed or recommended this round.** To make the other four
deletion-eligible, options: rsync batches to remote archive first, or confirm
each batch's evidence is fully ingested into the review queue/database with
a consistency check. Both are future decisions, not executed actions.
