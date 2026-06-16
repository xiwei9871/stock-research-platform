import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPlatformSummary, fetchReviewQueue } from '../api/client';
import type { EvidenceDigestAction, PlatformSummary, ReviewQueueGroup, ReviewQueueResponse } from '../api/types';
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

function formatRiskWarningCounts(riskCount: number, warningCount: number) {
  return `${riskCount} 风险 / ${warningCount} 提醒`;
}

function dateDiffDays(earlier: string, later: string) {
  const earlierTime = Date.parse(`${earlier}T00:00:00Z`);
  const laterTime = Date.parse(`${later}T00:00:00Z`);
  if (!Number.isFinite(earlierTime) || !Number.isFinite(laterTime)) return null;
  return Math.round((laterTime - earlierTime) / 86_400_000);
}

function reviewTierLabel(tier?: string | null) {
  if (tier === 'top5_focus') return 'Top5 重点复盘';
  if (tier === 'top10_watch') return 'Top6-10 观察';
  return '策略候选';
}

function sourceKindLabel(sourceKind: string) {
  const labels: Record<string, string> = {
    strategy: '策略',
    news: '新闻',
    research: '研报',
    market: '市场',
    factor: '因子'
  };
  return labels[sourceKind] ?? sourceKind;
}

function collectGroupFreshness(groups: ReviewQueueGroup[]) {
  return groups.map((group) => {
    const latestDates = group.items
      .map((item) => item.latest_trade_date ?? item.trade_date)
      .filter((date): date is string => Boolean(date));
    const latestDate = latestDates.length > 0 ? latestDates.sort().at(-1) ?? null : null;
    return {
      bucket: group.bucket,
      label: group.label,
      count: group.items.length,
      latestDate
    };
  });
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
  const [platformSummary, setPlatformSummary] = useState<PlatformSummary | null>(null);
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
      const nextQueue = await fetchReviewQueue({ limit: 10, lookbackDays: 90 });
      if (requestIdRef.current !== requestId) return;
      const selection = findInitialSelection(nextQueue);
      setQueue(nextQueue);
      setSelectedBucket(selection.selectedBucket);
      setSelectedQueueId(selection.selectedQueueId);
      fetchPlatformSummary()
        .then((summary) => {
          if (requestIdRef.current === requestId) {
            setPlatformSummary(summary);
          }
        })
        .catch(() => {
          if (requestIdRef.current === requestId) {
            setPlatformSummary(null);
          }
        });
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
  const groupFreshness = queue ? collectGroupFreshness(queue.groups) : [];
  const latestMarketDate = platformSummary?.latest_market_date ?? null;
  const freshnessLag =
    queue && latestMarketDate ? dateDiffDays(queue.trade_date, latestMarketDate) : null;

  const selectGroup = (group: ReviewQueueGroup) => {
    setSelectedBucket(group.bucket);
    setSelectedQueueId(group.items[0]?.queue_id ?? null);
  };

  const openAction = (action: EvidenceDigestAction) => {
    const baseContext = actionContext(action, selectedItem?.asset_id, selectedItem?.display_name, selectedItem?.trade_date);
    const context: StockEntryContext = selectedItem
      ? {
          ...baseContext,
          sourceWorkspace: action.workspace === 'stock' ? 'reviewQueue' : baseContext.sourceWorkspace,
          runId: selectedItem.run_id,
          digestKey: selectedItem.digest_key,
          sourceType: selectedItem.source_type,
          sourceName: selectedItem.source_name,
          scoreVersion: selectedItem.score_version,
          topnRank: selectedItem.topn_rank ?? selectedItem.rank
        }
      : baseContext;
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
    <section className="workspace-stack" aria-label="策略复盘队列">
      <header className="workspace-header">
        <h1>策略复盘队列</h1>
        <p className="muted">按启用策略复盘最近可用交易日的 Top5 / Top10，检查候选标的的证据、风险和后续查证入口。</p>
      </header>

      {loading ? <p className="muted">正在加载策略复盘队列...</p> : null}

      {error ? (
        <section className="workspace-band" aria-label="策略复盘队列错误">
          <p className="error-text">{error}</p>
          <button type="button" onClick={loadQueue}>
            重新加载复盘队列
          </button>
        </section>
      ) : null}

      {queue && !error ? (
        <>
          {queue.warnings.length > 0 ? (
            <section className="workspace-band" aria-label="策略复盘队列提醒">
              {queue.warnings.map((warning) => (
                <p className="error-text" key={warning}>
                  {warning}
                </p>
              ))}
            </section>
          ) : null}

          <section className="workspace-band" aria-label="策略复盘分组">
            <div className="workspace-stack">
              <div className="section-heading">
                <div>
                  <span className="muted">复盘日期</span>
                  <strong>{queue.trade_date}</strong>
                </div>
                <div>
                  <span className="muted">平台市场日期</span>
                  <strong>{latestMarketDate ?? '读取中'}</strong>
                </div>
                <div>
                  <span className="muted">复盘范围</span>
                  <strong>{queue.review_mode === 'strategy_topn' ? '启用策略 Top10' : queue.score_version}</strong>
                </div>
              </div>

              <div className="workspace-panel" aria-label="复盘队列新鲜度">
                <div className="section-heading">
                  <h2>数据新鲜度</h2>
                  {freshnessLag == null ? (
                    <span className="status-chip neutral">等待平台日期</span>
                  ) : freshnessLag > 0 ? (
                    <span className="status-chip warning">落后 {freshnessLag} 天</span>
                  ) : (
                    <span className="status-chip success">已同步</span>
                  )}
                </div>
                <p className={freshnessLag != null && freshnessLag > 0 ? 'error-text' : 'muted'}>
                  {freshnessLag == null
                    ? '正在读取平台最新市场日期，用于判断复盘队列是否过旧。'
                    : freshnessLag > 0
                      ? `复盘队列落后平台市场日期 ${freshnessLag} 个自然日，请检查复盘生成任务。`
                      : '复盘队列与平台市场日期一致。'}
                </p>
                <div className="tag-stack" aria-label="分策略新鲜度">
                  {groupFreshness.map((group) => (
                    <span className="status-chip neutral" key={group.bucket}>
                      {`${group.label}：最新 ${group.latestDate ?? '暂无'}，${group.count} 只`}
                    </span>
                  ))}
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

              <div className="tag-stack" aria-label="证据来源">
                {sourceKinds.length > 0 ? (
                  sourceKinds.map((sourceKind) => (
                    <span className="status-chip" key={sourceKind}>
                      {sourceKindLabel(sourceKind)}
                    </span>
                  ))
                ) : (
                  <span className="muted">暂无证据来源</span>
                )}
              </div>
            </div>
          </section>

          <section className="workspace-band" aria-label="当前策略复盘列表">
            <div className="section-heading">
              <h2>{selectedGroup?.label ?? '复盘标的'}</h2>
              <span className="muted">{queue.trade_date}</span>
            </div>

            {selectedGroup && selectedGroup.items.length === 0 ? (
              <p className="muted">{queue.trade_date} 暂无 {selectedGroup.label} 复盘标的。</p>
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
                    <span>评分 {formatScore(item.score)}</span>
                    <span className="status-chip">{reviewTierLabel(item.review_tier)}</span>
                    <span className="tag-stack" aria-label={`${item.display_name || item.asset_id} source coverage`}>
                      {item.source_kinds.length > 0 ? (
                        item.source_kinds.map((sourceKind) => (
                          <span className="status-chip" key={sourceKind}>
                            {sourceKindLabel(sourceKind)}
                          </span>
                        ))
                      ) : (
                        <span className="muted">暂无来源</span>
                      )}
                    </span>
                    <span>{formatRiskWarningCounts(item.risk_count, item.warning_count)}</span>
                    <span>{item.next_action_count} 个入口</span>
                  </button>
                ))}
              </div>
            ) : null}
          </section>

          <section className="workspace-band" role="region" aria-label="选中标的证据">
            {selectedItem && selectedDigest ? (
              <div className="workspace-stack">
                <div className="section-heading">
                  <div>
                    <h2>{selectedItem.digest_title || selectedDigest.title}</h2>
                    <p className="muted">
                      {selectedItem.strategy_name ? `${selectedItem.strategy_name} · ` : ''}
                      {selectedItem.display_name || selectedItem.asset_id} · 评分 {formatScore(selectedItem.score)} · {reviewTierLabel(selectedItem.review_tier)}
                    </p>
                  </div>
                  <span className="status-chip">{selectedDigest.bucket}</span>
                </div>

                {selectedItem.source_kinds.length > 0 ? (
                  <div className="tag-stack" aria-label="证据来源">
                    {selectedItem.source_kinds.map((sourceKind) => (
                      <span className="status-chip" key={sourceKind}>
                        {sourceKindLabel(sourceKind)}
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
                    <h3>风险提示</h3>
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
                    <h3>系统提醒</h3>
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
              <p className="muted">请选择一个复盘标的查看证据。</p>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}
