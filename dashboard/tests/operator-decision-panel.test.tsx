import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OperatorDecisionPanel } from '../src/components/OperatorDecisionPanel';

const apiMocks = vi.hoisted(() => ({
  createOperatorDecision: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.createOperatorDecision.mockResolvedValue({
    event_id: 'operator_decision:operator-decision-api-2026-06-12:0:abc',
    asset_id: '000001.SZ',
    stock_code: '000001.SZ',
    stock_name: '平安银行',
    decision_date: '2026-06-12',
    operator_action: 'watch',
    decision_status: 'open',
    decision_label: 'observe',
    run_id: 'eod-2026-06-12-local',
    digest_key: '2026-06-12:manual_v1:000001.SZ',
    review_item_snapshot_id: 'review_item_snapshot:abc',
    evidence_digest_snapshot_id: 'evidence_digest_snapshot:def',
    snapshot_linkage_status: 'linked',
    snapshot_linkage_warnings: [],
    workflow_effects: [
      { type: 'watchlist_item', status: 'upserted', watchlist_id: 'manual_review', asset_id: '000001.SZ' }
    ],
    warnings: []
  });
});

afterEach(() => {
  cleanup();
});

function renderPanel(overrides: Partial<Parameters<typeof OperatorDecisionPanel>[0]> = {}) {
  return render(
    <OperatorDecisionPanel
      assetId="000001.SZ"
      stockCode="000001.SZ"
      stockName="平安银行"
      decisionDate="2026-06-12"
      runId="eod-2026-06-12-local"
      digestKey="2026-06-12:manual_v1:000001.SZ"
      sourceType="score_topn"
      sourceName="manual_v1_topn"
      sourceContextEntry="evidence_digest"
      {...overrides}
    />
  );
}

describe('OperatorDecisionPanel', () => {
  it('renders allowed manual research actions without trading words', () => {
    const { container } = renderPanel();

    expect(screen.getByRole('heading', { name: '复盘决策' })).toBeInTheDocument();
    const actionGroup = screen.getByRole('group', { name: '复盘动作' });

    expect(within(actionGroup).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '观察',
      '跳过',
      '跟踪',
      '加入影子池',
      '备注',
      '关闭'
    ]);
    expect(container).not.toHaveTextContent(/\bbuy\b/i);
    expect(container).not.toHaveTextContent(/\bsell\b/i);
    expect(container).not.toHaveTextContent(/\btrade\b/i);
    expect(container).not.toHaveTextContent(/\border\b/i);
    expect(container).not.toHaveTextContent(/\bposition\b/i);
  });

  it('submits a note with digest lineage and shows linked snapshot status', async () => {
    const onDecisionCreated = vi.fn();
    renderPanel({ onDecisionCreated });

    fireEvent.change(screen.getByLabelText('operator note'), {
      target: { value: '观察回踩确认' }
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    await waitFor(() => expect(apiMocks.createOperatorDecision).toHaveBeenCalledTimes(1));
    expect(apiMocks.createOperatorDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: '000001.SZ',
        stock_code: '000001.SZ',
        stock_name: '平安银行',
        decision_date: '2026-06-12',
        operator_action: 'watch',
        operator_note: '观察回踩确认',
        run_id: 'eod-2026-06-12-local',
        digest_key: '2026-06-12:manual_v1:000001.SZ',
        source_type: 'score_topn',
        source_name: 'manual_v1_topn',
        source_context: { entry: 'evidence_digest' }
      })
    );
    expect(await screen.findByText('复盘已保存')).toBeInTheDocument();
    expect(screen.getByText('已加入人工观察池')).toBeInTheDocument();
    expect(screen.getByText('证据快照已关联')).toBeInTheDocument();
    expect(screen.getByText(/operator_decision:operator-decision-api/)).toBeInTheDocument();
    expect(onDecisionCreated).toHaveBeenCalledWith(expect.objectContaining({ snapshot_linkage_status: 'linked' }));
  });

  it('shows missing snapshot warnings without treating the save as failed', async () => {
    apiMocks.createOperatorDecision.mockResolvedValueOnce({
      event_id: 'operator_decision:missing',
      asset_id: '000001.SZ',
      stock_code: '000001.SZ',
      stock_name: '平安银行',
      decision_date: '2026-06-12',
      operator_action: 'note',
      decision_status: 'open',
      decision_label: 'observe',
      run_id: 'eod-2026-06-12-local',
      digest_key: 'missing-digest',
      review_item_snapshot_id: '',
      evidence_digest_snapshot_id: '',
      snapshot_linkage_status: 'missing',
      snapshot_linkage_warnings: ['No evidence_digest_snapshot found for run_id + digest_key'],
      workflow_effects: [],
      warnings: ['No evidence_digest_snapshot found for run_id + digest_key']
    });
    renderPanel();

    fireEvent.click(screen.getByRole('button', { name: '备注' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(await screen.findByText('复盘已保存')).toBeInTheDocument();
    expect(screen.getByText('证据快照缺失')).toBeInTheDocument();
    expect(screen.getByText('No evidence_digest_snapshot found for run_id + digest_key')).toBeInTheDocument();
    expect(screen.queryByText('Decision save failed')).not.toBeInTheDocument();
  });

  it('shows API errors clearly', async () => {
    apiMocks.createOperatorDecision.mockRejectedValueOnce(new Error('POST /api/operator-decisions failed with 400'));
    renderPanel();

    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(await screen.findByText('Decision save failed')).toBeInTheDocument();
    expect(screen.getByText('POST /api/operator-decisions failed with 400')).toBeInTheDocument();
  });
});
