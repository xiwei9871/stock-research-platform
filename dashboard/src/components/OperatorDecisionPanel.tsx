import { FormEvent, useState } from 'react';
import { createOperatorDecision } from '../api/client';
import type { CreateOperatorDecisionResponse } from '../api/types';

const ACTIONS = ['watch', 'skip', 'follow_up', 'add_to_shadow', 'note', 'close'] as const;

type OperatorAction = (typeof ACTIONS)[number];

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

export function OperatorDecisionPanel({
  assetId,
  stockCode,
  stockName,
  decisionDate,
  runId,
  digestKey,
  reviewItemSnapshotId,
  evidenceDigestSnapshotId,
  sourceType,
  sourceName,
  sourceContextEntry,
  onDecisionCreated
}: OperatorDecisionPanelProps) {
  const [operatorAction, setOperatorAction] = useState<OperatorAction>('watch');
  const [operatorNote, setOperatorNote] = useState('');
  const [followUpDate, setFollowUpDate] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<CreateOperatorDecisionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submitDecision = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const response = await createOperatorDecision({
        asset_id: assetId,
        stock_code: stockCode ?? assetId,
        stock_name: stockName,
        decision_date: decisionDate,
        operator_action: operatorAction,
        decision_status: 'open',
        operator_note: operatorNote,
        follow_up_date: followUpDate || undefined,
        run_id: runId,
        digest_key: digestKey,
        review_item_snapshot_id: reviewItemSnapshotId,
        evidence_digest_snapshot_id: evidenceDigestSnapshotId,
        source_type: sourceType,
        source_name: sourceName,
        source_context: {
          entry: sourceContextEntry
        }
      });
      setResult(response);
      onDecisionCreated?.(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  const warnings = result?.warnings?.length ? result.warnings : result?.snapshot_linkage_warnings ?? [];
  const snapshotStatus = result?.snapshot_linkage_status;

  return (
    <section className="operator-decision-panel" aria-label="Operator Decision Panel">
      <h2>Operator Decision</h2>
      <form className="workspace-stack" onSubmit={submitDecision}>
        <div className="compact-toolbar">
          <label>
            Action
            <select
              aria-label="operator action"
              value={operatorAction}
              onChange={(event) => setOperatorAction(event.target.value as OperatorAction)}
            >
              {ACTIONS.map((action) => (
                <option key={action} value={action}>
                  {action}
                </option>
              ))}
            </select>
          </label>
          <label>
            Follow-up date
            <input
              aria-label="follow up date"
              type="date"
              value={followUpDate}
              onChange={(event) => setFollowUpDate(event.target.value)}
            />
          </label>
        </div>
        <label>
          Note
          <textarea
            aria-label="operator note"
            rows={3}
            value={operatorNote}
            onChange={(event) => setOperatorNote(event.target.value)}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Saving decision...' : 'Save decision'}
        </button>
      </form>

      {result ? (
        <div className="evidence-row">
          <div>
            <strong>Decision saved</strong>
            <span>{result.event_id}</span>
          </div>
          <p>{snapshotStatus === 'linked' ? 'Snapshot linked' : 'Snapshot missing'}</p>
          {warnings.length > 0 ? (
            <div className="tag-stack">
              {warnings.map((warning) => (
                <span className="status-chip warning" key={warning}>
                  {warning}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <div className="evidence-row">
          <div>
            <strong>Decision save failed</strong>
          </div>
          <p className="error-text">{error}</p>
        </div>
      ) : null}
    </section>
  );
}
