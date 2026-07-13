import { FormEvent, useState } from 'react';
import { createOperatorDecision } from '../api/client';
import type { CreateOperatorDecisionResponse } from '../api/types';

const ACTIONS = ['watch', 'skip', 'follow_up', 'add_to_shadow', 'note', 'close'] as const;

type OperatorAction = (typeof ACTIONS)[number];
type WorkflowEffect = NonNullable<CreateOperatorDecisionResponse['workflow_effects']>[number];

const ACTION_LABELS: Record<OperatorAction, string> = {
  watch: '观察',
  skip: '跳过',
  follow_up: '跟踪',
  add_to_shadow: '加入影子池',
  note: '备注',
  close: '关闭'
};

const ACTION_DECISION_LABELS: Record<OperatorAction, string> = {
  watch: 'observe',
  skip: 'no_action',
  follow_up: 'observe',
  add_to_shadow: 'candidate',
  note: 'observe',
  close: 'remove'
};

function workflowEffectLabel(effect: WorkflowEffect) {
  if (effect.type === 'watchlist_item' && effect.status === 'upserted') return '已加入人工观察池';
  if (effect.type === 'watchlist_item' && effect.status === 'deactivated') return '已关闭人工观察';
  return `${effect.type}:${effect.status}`;
}

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
        decision_label: ACTION_DECISION_LABELS[operatorAction],
        decision_status: 'open',
        evidence_artifact_id: digestKey ? `evidence_digest:${digestKey}` : undefined,
        operator_note: operatorNote,
        follow_up_date: followUpDate || undefined,
        run_id: runId,
        digest_key: digestKey,
        review_item_snapshot_id: reviewItemSnapshotId,
        evidence_digest_snapshot_id: evidenceDigestSnapshotId,
        source_type: sourceType,
        source_name: sourceName,
        manual_review_required: true,
        auto_trade_enabled: false,
        source_context: {
          entry: sourceContextEntry,
          run_id: runId,
          digest_key: digestKey,
          review_item_snapshot_id: reviewItemSnapshotId,
          evidence_digest_snapshot_id: evidenceDigestSnapshotId
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
  const workflowEffects = result?.workflow_effects ?? [];

  return (
    <section className="operator-decision-panel" aria-label="Operator Decision Panel">
      <h2>复盘决策</h2>
      <form className="workspace-stack" onSubmit={submitDecision}>
        <div className="decision-action-grid" role="group" aria-label="复盘动作">
          {ACTIONS.map((action) => (
            <button
              key={action}
              type="button"
              className={operatorAction === action ? 'active' : ''}
              aria-pressed={operatorAction === action}
              onClick={() => setOperatorAction(action)}
            >
              {ACTION_LABELS[action]}
            </button>
          ))}
        </div>
        <div className="compact-toolbar">
          <label>
            跟踪日期
            <input
              aria-label="follow up date"
              type="date"
              value={followUpDate}
              onChange={(event) => setFollowUpDate(event.target.value)}
            />
          </label>
        </div>
        <label>
          复盘备注
          <textarea
            aria-label="operator note"
            rows={3}
            value={operatorNote}
            onChange={(event) => setOperatorNote(event.target.value)}
          />
        </label>
        <button type="submit" aria-label="Save decision" disabled={submitting}>
          {submitting ? '正在保存...' : '保存决策'}
        </button>
      </form>

      {result ? (
        <div className="evidence-row">
          <div>
            <strong>复盘已保存</strong>
            <span>{result.event_id}</span>
          </div>
          <p>{snapshotStatus === 'linked' ? '证据快照已关联' : '证据快照缺失'}</p>
          {workflowEffects.length > 0 ? (
            <div className="tag-stack">
              {workflowEffects.map((effect) => (
                <span
                  className={effect.status === 'upserted' ? 'status-chip positive' : 'status-chip neutral'}
                  key={`${effect.type}-${effect.status}-${effect.asset_id ?? ''}`}
                >
                  {workflowEffectLabel(effect)}
                </span>
              ))}
            </div>
          ) : null}
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
