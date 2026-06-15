# Operator Decision UI v1

## Scope

Batch G adds the smallest useful UI for local operator decisions:

- a lightweight `OperatorDecisionPanel`
- mounting in Stock Workspace near Evidence Digest
- POST through `createOperatorDecision`
- linked/missing snapshot status display
- non-blocking warnings for missing snapshots
- decision history refresh by reloading the current stock profile

The UI records human research decisions only. It does not create orders, positions, execution instructions, or automatic trading signals.

## Out Of Scope

- HomeCockpit redesign
- Strategy Command Center or Backtest Lab changes
- new strategies, factors, or data sources
- broker/account/position/order UI
- permission system
- Review Queue page redesign
- Evidence Digest page redesign
- buy/sell/trade/execution wording

## Current API Capability

Batch F provides:

- `POST /api/operator-decisions`
- `CreateOperatorDecisionRequest`
- `CreateOperatorDecisionResponse`
- `createOperatorDecision(request)`

The response includes:

- `event_id`
- `decision_label`
- `snapshot_linkage_status`
- `snapshot_linkage_warnings`
- `review_item_snapshot_id`
- `evidence_digest_snapshot_id`

Existing Stock Workspace already renders `profile.decisions` under Review / Outcomes, so a successful write can refresh the profile to read back the persisted decision.

## Mounting Position

Primary mount:

- Stock Workspace
- inside the Evidence Digest region
- below digest facts/actions

Reason:

- Evidence Digest is the "single stock before review" page.
- It has the asset profile, current trade date, digest lineage, warnings, and existing decision history nearby.
- It avoids HomeCockpit and does not require a Review Queue layout rewrite.

Review Queue integration is limited to passing lineage when opening Stock Workspace.

## Component

Create:

```text
dashboard/src/components/OperatorDecisionPanel.tsx
```

Props:

```ts
type OperatorDecisionPanelProps = {
  assetId: string;
  stockCode?: string;
  stockName?: string;
  decisionDate: string;
  runId?: string;
  digestKey?: string;
  reviewItemSnapshotId?: string;
  evidenceDigestSnapshotId?: string;
  sourceType?: string;
  sourceName?: string;
  sourceContextEntry: 'review_queue' | 'evidence_digest' | string;
  onDecisionCreated?: (response: CreateOperatorDecisionResponse) => void;
};
```

## Form Fields

Visible fields:

- `operator_action`
- `operator_note`
- `follow_up_date`

Default fields:

- `decision_status = open`

Allowed visible actions:

- `watch`
- `skip`
- `follow_up`
- `add_to_shadow`
- `note`
- `close`

Forbidden visible wording:

- buy
- sell
- trade
- execute
- order
- position

## Source Context Rules

Stock Workspace passes:

- `asset_id`
- `stock_code`
- `stock_name`
- `decision_date`
- `run_id`
- `digest_key`
- `review_item_snapshot_id`
- `evidence_digest_snapshot_id`
- `source_type`
- `source_name`
- `source_context.entry`

Evidence Digest values are preferred when available. Review Queue handoff values fill gaps.

Review Queue handoff adds these optional fields to `StockEntryContext`:

- `runId`
- `digestKey`
- `sourceType`
- `sourceName`
- `reviewItemSnapshotId`
- `evidenceDigestSnapshotId`
- `scoreVersion`
- `topnRank`

## Linked / Missing Display

After a successful POST:

- display `Decision saved`
- display `event_id`
- display `Snapshot linked` when `snapshot_linkage_status = linked`
- display `Snapshot missing` and warnings when status is `missing`

Missing snapshots are warnings, not UI errors.

API errors are shown as an error message and do not append a local decision.

## Tests

Focused tests:

- panel renders
- action selector only shows allowed actions
- forbidden trading words are absent
- note submission calls `createOperatorDecision`
- linked response displays linked state
- missing response displays warning
- API error displays error
- Stock Workspace passes Evidence Digest lineage
- Review Queue passes selected candidate lineage into Stock Workspace context
- dashboard client tests remain green

## Smoke Test

1. Start dashboard API and frontend.
2. Open Stock Workspace from Review Queue or direct nav.
3. Wait for Evidence Digest.
4. Choose `watch` or `note`.
5. Submit a short note.
6. Confirm saved event id and snapshot linked/missing status.
7. Confirm Review / Outcomes updates after profile reload.

## Batch H Reserve

- richer decision history cards with source-context chips
- one-click decision presets from Review Queue list rows
- edit/close flow for existing decisions
- outcome follow-up UI
