import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchReviewQueue } from '../api/client';
import type { EvidenceDigestAction, ReviewQueueGroup, ReviewQueueResponse } from '../api/types';
import type { StockEntryContext } from './StockWorkspace';

type ReviewQueueWorkspaceProps = {
  onOpenStock?: (assetId: string, context?: StockEntryContext) => void;
  onOpenNews?: (context: StockEntryContext) => void;
  onOpenResearchReports?: (context: StockEntryContext) => void;
  onOpenMarketMonitor?: (context: StockEntryContext) => void;
};

function formatScore(score: number | null) {
  return typeof score === 'number' ? score.toFixed(1) : '-';
}

function findInitialSelection(queue: ReviewQueueResponse) {
  const selectedGroup = queue.groups.find((group) => group.items.length > 0) ?? queue.groups[0] ?? null;
  return {
    selectedBucket: selectedGroup?.bucket ?? 'strong',
    selectedQueueId: selectedGroup?.items[0]?.queue_id ?? null
  };
}

function collectSourceKinds(queue: ReviewQueueResponse) {
  const sourceKinds: string[] = [];
  const seen = new Set<string>();

  for (const group of queue.groups) {
    for (const item of group.items) {
      for (const sourceKind of item.source_kinds) {
        if (!seen.has(sourceKind)) {
          seen.add(sourceKind);
          sourceKinds.push(sourceKind);
        }
      }
    }
  }

  return sourceKinds;
}

function formatCount(count: number, singular: string) {
  return `${count} ${singular}${count === 1 ? '' : 's'}`;
}

function actionContext(
  action: EvidenceDigestAction,
  fallbackAssetId?: string,
  fallbackQuery?: string,
  fallbackTradeDate?: string
): StockEntryContext {
  return {
    sourceWorkspace: action.workspace === 'stock' ? 'search' : (action.workspace as StockEntryContext['sourceWorkspace']),
    assetId: action.asset_id ?? fallbackAssetId,
    query: action.query ?? fallbackQuery ?? action.asset_id ?? fallbackAssetId,
    newsId: action.news_id,
    reportId: action.report_id,
    eventKey: action.event_key,
    monitorTab: action.monitor_tab as string | undefined,
    tradeDate: fallbackTradeDate
  };
}

export function ReviewQueueWorkspace({
  onOpenStock,
  onOpenNews,
  onOpenResearchReports,
  onOpenMarketMonitor
}: ReviewQueueWorkspaceProps) {
  const [queue, setQueue] = useState<ReviewQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedBucket, setSelectedBucket] = useState<string>('strong');
  const [selectedQueueId, setSelectedQueueId] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const loadQueue = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError(null);

    try {
      const nextQueue = await fetchReviewQueue({ limit: 20, lookbackDays: 90 });
      if (requestIdRef.current !== requestId) return;
      const selection = findInitialSelection(nextQueue);
      setQueue(nextQueue);
      setSelectedBucket(selection.selectedBucket);
      setSelectedQueueId(selection.selectedQueueId);
    } catch (caught) {
      if (requestIdRef.current !== requestId) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadQueue();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadQueue]);

  const selectedGroup =
    queue?.groups.find((group) => group.bucket === selectedBucket) ?? queue?.groups[0] ?? null;
  const selectedItem =
    selectedGroup?.items.find((item) => item.queue_id === selectedQueueId) ?? selectedGroup?.items[0] ?? null;
  const selectedDigest = selectedItem?.digest ?? null;
  const sourceKinds = queue ? collectSourceKinds(queue) : [];

  const selectGroup = (group: ReviewQueueGroup) => {
    setSelectedBucket(group.bucket);
    setSelectedQueueId(group.items[0]?.queue_id ?? null);
  };

  const openAction = (action: EvidenceDigestAction) => {
    const context = actionContext(action, selectedItem?.asset_id, selectedItem?.display_name, selectedItem?.trade_date);
    const assetId = context.assetId ?? selectedItem?.asset_id ?? '';

    if (action.workspace === 'stock') {
      if (assetId) onOpenStock?.(assetId, context);
    } else if (action.workspace === 'news') {
      onOpenNews?.(context);
    } else if (action.workspace === 'researchReports') {
      onOpenResearchReports?.(context);
    } else if (action.workspace === 'market') {
      onOpenMarketMonitor?.(context);
    }
  };

  return (
    <section className="workspace-stack" aria-label="Review Queue workspace">
      <header className="workspace-header">
        <h1>Review Queue</h1>
        <p className="muted">Daily evidence digest inbox for validating strategy candidates and opening source-backed next steps.</p>
      </header>

      {loading ? <p className="muted">Loading review queue...</p> : null}

      {error ? (
        <section className="workspace-band" aria-label="Review Queue Error">
          <p className="error-text">{error}</p>
          <button type="button" onClick={loadQueue}>
            Retry Review Queue
          </button>
        </section>
      ) : null}

      {queue && !error ? (
        <>
          {queue.warnings.length > 0 ? (
            <section className="workspace-band" aria-label="Review Queue Warnings">
              {queue.warnings.map((warning) => (
                <p className="error-text" key={warning}>
                  {warning}
                </p>
              ))}
            </section>
          ) : null}

          <section className="workspace-band" aria-label="Review Queue Groups">
            <div className="workspace-stack">
              <div className="section-heading">
                <div>
                  <span className="muted">Trade Date</span>
                  <strong>{queue.trade_date}</strong>
                </div>
                <div>
                  <span className="muted">Score Version</span>
                  <strong>{queue.score_version}</strong>
                </div>
              </div>

              <div className="compact-toolbar">
                {queue.groups.map((group) => (
                  <button
                    key={group.bucket}
                    type="button"
                    aria-pressed={group.bucket === selectedGroup?.bucket}
                    onClick={() => selectGroup(group)}
                  >
                    {group.label} {group.count}
                  </button>
                ))}
              </div>

              <div className="tag-stack" aria-label="Source Filters">
                {sourceKinds.length > 0 ? (
                  sourceKinds.map((sourceKind) => (
                    <span className="status-chip" key={sourceKind}>
                      {sourceKind}
                    </span>
                  ))
                ) : (
                  <span className="muted">No source filters</span>
                )}
              </div>
            </div>
          </section>

          <section className="workspace-band" aria-label="Selected Queue Group">
            <div className="section-heading">
              <h2>{selectedGroup?.label ?? 'Queue Items'}</h2>
              <span className="muted">{queue.trade_date}</span>
            </div>

            {selectedGroup && selectedGroup.items.length === 0 ? (
              <p className="muted">No {selectedGroup.label.toLowerCase()} items for {queue.trade_date}.</p>
            ) : null}

            {selectedGroup && selectedGroup.items.length > 0 ? (
              <div className="data-table" aria-label={`${selectedGroup.label} queue items`}>
                {selectedGroup.items.map((item) => (
                  <button
                    key={item.queue_id}
                    type="button"
                    className="data-table-row"
                    style={{
                      gridTemplateColumns: '48px minmax(180px, 1.4fr) 92px 96px minmax(120px, 0.8fr) 96px 104px'
                    }}
                    aria-pressed={item.queue_id === selectedItem?.queue_id}
                    onClick={() => setSelectedQueueId(item.queue_id)}
                  >
                    <span>#{item.rank ?? '-'}</span>
                    <span>
                      <strong>{item.display_name || item.asset_id}</strong>
                      <span className="muted">{item.asset_id}</span>
                      <span>{item.digest_title || item.digest.title}</span>
                    </span>
                    <span>Score {formatScore(item.score)}</span>
                    <span className="status-chip">{item.bucket}</span>
                    <span className="tag-stack" aria-label={`${item.display_name || item.asset_id} source coverage`}>
                      {item.source_kinds.length > 0 ? (
                        item.source_kinds.map((sourceKind) => (
                          <span className="status-chip" key={sourceKind}>
                            {sourceKind}
                          </span>
                        ))
                      ) : (
                        <span className="muted">No sources</span>
                      )}
                    </span>
                    <span>
                      <span>{formatCount(item.risk_count, 'risk')}</span>
                      <span>{formatCount(item.warning_count, 'warning')}</span>
                    </span>
                    <span>{item.next_action_count} actions</span>
                  </button>
                ))}
              </div>
            ) : null}
          </section>

          <section className="workspace-band" role="region" aria-label="Selected Evidence">
            {selectedItem && selectedDigest ? (
              <div className="workspace-stack">
                <div className="section-heading">
                  <div>
                    <h2>{selectedItem.digest_title || selectedDigest.title}</h2>
                    <p className="muted">
                      {selectedItem.display_name || selectedItem.asset_id} · score {formatScore(selectedItem.score)}
                    </p>
                  </div>
                  <span className="status-chip">{selectedDigest.bucket}</span>
                </div>

                {selectedItem.source_kinds.length > 0 ? (
                  <div className="tag-stack" aria-label="Evidence sources">
                    {selectedItem.source_kinds.map((sourceKind) => (
                      <span className="status-chip" key={sourceKind}>
                        {sourceKind}
                      </span>
                    ))}
                  </div>
                ) : null}

                {selectedDigest.facts.length > 0 ? (
                  <div className="stock-evidence-grid">
                    {selectedDigest.facts.map((fact, index) => (
                      <article key={`${fact.kind}-${fact.label}-${index}`}>
                        <span className="status-chip">{fact.kind}</span>
                        <p>{fact.label}</p>
                        {fact.value != null ? <p className="muted">{String(fact.value)}</p> : null}
                      </article>
                    ))}
                  </div>
                ) : null}

                {selectedDigest.risk_flags.length > 0 ? (
                  <div>
                    <h3>Risk Flags</h3>
                    <div className="tag-stack">
                      {selectedDigest.risk_flags.map((risk) => (
                        <span className="status-chip" key={risk.key}>
                          {risk.label}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {selectedDigest.warnings.length > 0 ? (
                  <div>
                    <h3>Warnings</h3>
                    {selectedDigest.warnings.map((warning) => (
                      <p className="error-text" key={warning}>
                        {warning}
                      </p>
                    ))}
                  </div>
                ) : null}

                {selectedDigest.next_actions.length > 0 ? (
                  <div className="compact-toolbar">
                    {selectedDigest.next_actions.map((action) => (
                      <button key={action.key} type="button" onClick={() => openAction(action)}>
                        {action.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="muted">Select a queue item to review its evidence.</p>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}
