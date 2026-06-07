# Tech Bottleneck Targeted P2 Evidence Backfill Design

## Goal

Build a targeted evidence-completion step for the current core-tech top100 P2 queue. The goal is to determine whether the five P2 assets can be promoted to strict P1 by adding product-family bridge evidence and point-in-time safe supporting evidence, without expanding the universe or loosening the P1 rule.

Current P2 assets:

- 洁美科技 `CN:SZ:002859`
- 精测电子 `CN:SZ:300567`
- 天孚通信 `CN:SZ:300394`
- 北方华创 `CN:SZ:002371`
- 奥普特 `CN:SH:688686`

All current P2 rows are blocked by:

`needs_product_family_mapping`

This means the system sees credible bottleneck and technical evidence, but cannot link product exposure and semantic evidence into the same product family.

## Scope

In scope:

- Audit current evidence lineage for the five P2 assets.
- Generate deterministic product-family bridge suggestions.
- Produce targeted bridge evidence rows when the bridge is point-in-time safe.
- Re-run strict quality review with the added bridge evidence.
- Produce a promotion delta report that explains which P2 assets move to P1 and why.

Out of scope:

- Full-market scanning.
- Changing the strict P1 auto-approval rule.
- Manual approval into P1.
- Return testing.
- Broad web/news scraping for every candidate.

## Inputs

Primary input directory:

`outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/`

Required input files:

- `quality_review/human_review_assets.csv`
- `quality_review/quality_review.csv`
- `core_tech_gate/core_tech_candidates.csv`
- `../pilot_top50_20250101_20260607/combined_evidence_with_official_product/evidence.csv`
- `../pilot_top50_20250101_20260607/official_product_backfill/product_evidence.csv`

The backfill step should only process rows where:

- `p3_decision == needs_product_family_mapping`
- `review_priority == P2_mapping_review`
- `next_evidence_need == needs_product_family_mapping`

## Product-Family Bridge Targets

The bridge mapper should focus on the current five assets and their known likely families:

- 洁美科技: `semiconductor_materials_components`
  - Product terms: 载带, 离型膜, MLCC离型膜, 半导体材料, 电子元件材料
  - Semantic bridge terms: 国产替代, 技术壁垒, 客户认证, 产能, 半导体封装

- 精测电子: `semiconductor_testing_metrology`
  - Product terms: 半导体检测, 量测设备, AOI, 测试设备, 面板检测
  - Semantic bridge terms: 国产替代, 先进封装, 技术壁垒, 客户导入, 产能

- 天孚通信: `optical_communication_components`
  - Product terms: 光器件, 光模块, 高速光引擎, CPO, 光通信器件
  - Semantic bridge terms: 国产替代, 高速率, AI算力, 客户导入, 量产

- 北方华创: `semiconductor_equipment`
  - Product terms: 刻蚀, PVD, CVD, 清洗设备, 热处理设备, 半导体设备
  - Semantic bridge terms: 国产替代, 先进制程, 技术壁垒, 客户导入, 产能

- 奥普特: `semiconductor_testing_metrology`
  - Product terms: 机器视觉, AOI, 检测设备, 半导体检测应用, 视觉检测
  - Semantic bridge terms: 国产替代, 半导体, 客户导入, 技术壁垒, 量产

These bridge targets should be encoded as a deterministic mapping table, not as free-form manual decisions.

## Evidence Lineage Audit

For each P2 asset and candidate date, output:

- Existing product evidence count by product family.
- Existing bottleneck evidence count by matched product family.
- Existing technical evidence count by matched product family.
- Existing capacity/customer/catalyst support evidence count.
- Current blocker reason.
- Candidate bridge family.
- Missing bridge side:
  - `missing_product_family_on_product_evidence`
  - `missing_product_family_on_semantic_evidence`
  - `product_and_semantic_family_mismatch`
  - `insufficient_pit_safe_bridge_evidence`

This output explains why quality review did not connect the evidence before the targeted step.

## Bridge Evidence Rules

The bridge step may create bridge evidence only when:

- The candidate date is known.
- The source evidence date is on or before the candidate date.
- The original row is `as_of_safe == True`, or the source date is otherwise clearly safe.
- Product terms and semantic bridge terms co-occur in existing evidence snippets, titles, or product rows for the same asset and candidate date.

Generated bridge rows must be labeled as derived evidence:

- `source_type = derived_product_family_bridge`
- `evidence_type = product_revenue_exposure` or the original semantic evidence type being bridged
- `matched_keyword = <family>:<matched_terms>`
- `is_proxy = True`
- `as_of_safe = True`
- `metadata_json` includes:
  - `bridge_family`
  - `bridge_reason`
  - `source_evidence_ids` if available
  - `source_candidate_trade_date`

The bridge step must not fabricate new facts. It only normalizes and links already available point-in-time safe evidence.

## Re-Review

After bridge evidence is added:

1. Combine original evidence with bridge evidence.
2. Re-run strict `tech_bottleneck_quality_review`.
3. Compare before and after:
   - P2 to P1 promotions.
   - P2 still blocked.
   - New rejection reasons if any.

The strict auto-approval rule remains unchanged.

## Outputs

Output directory:

`outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/`

Required files:

- `targeted_evidence_gap_audit.csv`
- `product_family_bridge_suggestions.csv`
- `targeted_backfill_evidence.csv`
- `combined_evidence_after_targeted_backfill.csv`
- `quality_review_after_targeted_backfill.csv`
- `promotion_delta.md`
- `manifest.json`

`promotion_delta.md` should include:

- P2 asset count before.
- P1 asset count before.
- P1 asset count after.
- Assets promoted from P2 to P1.
- Assets still blocked, grouped by `next_evidence_need`.
- Evidence rows added by family and source type.

## Success Criteria

The step is successful if it produces a clear answer for each P2 asset:

- Promoted to P1 because same-product-family linkage is now closed.
- Still P2 because bridge evidence is insufficient.
- Rejected because the bridge revealed no real same-family bottleneck chain.

The output should make the next action obvious: either accept the new P1, continue automated source backfill for a specific missing field, or drop the asset from the tech-bottleneck queue.

## Risks

Primary risk:

- Over-bridging could convert weak semantic similarity into false evidence linkage.

Mitigations:

- Bridge only existing point-in-time safe evidence.
- Mark bridge rows as proxy/derived.
- Keep strict quality review unchanged.
- Emit lineage audit before promotion delta.

## Approval

This design is approved for implementation planning once reviewed by the user.
