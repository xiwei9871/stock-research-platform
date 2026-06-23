import { useEffect, useState } from 'react';
import {
  fetchBacktestStrategies,
  fetchMarketMonitorEod,
  fetchPlatformReadiness,
  fetchPlatformSummary,
  fetchPublicNews,
  fetchStrategyScoreAudit
} from '../api/client';
import type {
  MarketMonitorPayload,
  PlatformReadiness,
  PlatformReadinessHealthGroup,
  PlatformReadinessHealthItem,
  PlatformSummary,
  PublicNewsItem,
  StrategyScoreAuditSummary,
  StrategyCatalogItem
} from '../api/types';

type WorkspaceMode =
  | 'reviewQueue'
  | 'market'
  | 'news'
  | 'researchReports'
  | 'stock'
  | 'watchlist'
  | 'factors'
  | 'strategyLab'
  | 'generatedReports';

type HomeCockpitProps = {
  onNavigate: (mode: WorkspaceMode) => void;
};

const ACTIVE_STRATEGY_IDS = ['lhb_shortline', 'mid_trend', 'tech_bottleneck'];

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '-';
}

function formatPercent(value: number | null | undefined, options: { signed?: boolean } = {}) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  const prefix = options.signed && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(1)}%`;
}

function formatOneDecimal(value: number | null | undefined) {
  return typeof value === 'number' && !Number.isNaN(value) ? value.toFixed(1) : '-';
}

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' && !Number.isNaN(value) ? `${value.toFixed(1)} 分` : '-';
}

function formatRatio(value: number | null | undefined) {
  return typeof value === 'number' && !Number.isNaN(value) ? `${(value * 100).toFixed(1)}%` : '-';
}

function formatState(value: string | null | undefined) {
  if (!value) return '-';
  const labels: Record<string, string> = {
    hot: '偏热',
    warm: '回暖',
    neutral: '中性',
    cold: '偏冷',
    weak: '偏弱',
    reduced: '降低仓位',
    normal: '正常仓位',
    expanded: '提高仓位'
  };
  return labels[value] ?? value.charAt(0).toUpperCase() + value.slice(1).replaceAll('_', ' ');
}

function formatReadinessValue(value: string) {
  const labels: Record<string, string> = {
    ok: '正常',
    blocked: '阻塞',
    ready: '正常',
    partial: '部分可用',
    missing_data: '缺少数据',
    unknown: '未知'
  };
  const normalized = value.toLowerCase();
  return labels[normalized] ?? value;
}

function readinessStatusClass(value: string | null | undefined) {
  const normalized = String(value ?? '').toLowerCase();
  if (normalized === 'ok' || normalized === 'ready' || normalized === 'success') return 'ready';
  if (normalized === 'partial' || normalized === 'unknown' || normalized === 'skipped') return 'partial';
  if (normalized === 'blocked' || normalized === 'missing_data' || normalized === 'failed' || normalized === 'unavailable') {
    return 'blocked';
  }
  return 'partial';
}

function platformRiskStatus(readiness: PlatformReadiness | null) {
  if (!readiness) return '-';
  if (readiness.status === 'BLOCKED') return '阻塞';
  if (readiness.status === 'PARTIAL' || (readiness.warnings ?? []).length > 0) return '需关注';
  return '正常';
}

function healthGroup(readiness: PlatformReadiness | null, key: string): PlatformReadinessHealthGroup | null {
  return readiness?.health_groups?.find((group) => group.key === key) ?? null;
}

function readinessCount(group: PlatformReadinessHealthGroup | null, fallbackTotal = 0) {
  if (!group) return `-/${fallbackTotal || '-'}`;
  return `${group.ready_count}/${group.total_count}`;
}

function healthItemDetail(item: PlatformReadinessHealthItem) {
  if (item.detail) return item.detail;
  if (item.latest_trade_date && typeof item.row_count === 'number') return `${item.latest_trade_date}，${item.row_count.toLocaleString()} rows`;
  if (item.latest_trade_date) return item.latest_trade_date;
  if (typeof item.row_count === 'number') return `${item.row_count.toLocaleString()} rows`;
  return '暂无详情';
}

function formatMode(value: string) {
  const labels: Record<string, string> = {
    eod_local: '本地日线',
    eod: '日线',
    realtime: '实时'
  };
  return labels[value] ?? value;
}

function formatReadinessWarning(value: string) {
  const labels: Record<string, string> = {
    'Platform summary unavailable': '平台摘要不可用',
    'Review Queue unavailable': '复盘队列不可用',
    'News unavailable': '新闻不可用',
    'Research Reports unavailable': '研报不可用',
    'Generated Reports unavailable': '生成报告不可用',
    'TopN preview unavailable': 'TopN 预览不可用'
  };
  return labels[value] ?? value;
}

function strategyScoreAuditStatusLabel(audit: StrategyScoreAuditSummary | null) {
  if (!audit) return '-';
  if (audit.overall_status === 'ok') return '正常';
  if (audit.overall_status === 'warning') return '需关注';
  if (audit.overall_status === 'missing') return '待补齐';
  return audit.overall_status;
}

function strategyScoreAuditStatusClass(audit: StrategyScoreAuditSummary | null) {
  if (!audit) return 'partial';
  if (audit.overall_status === 'ok') return 'ready';
  if (audit.overall_status === 'warning') return 'partial';
  if (audit.overall_status === 'missing') return 'blocked';
  return 'partial';
}

function strategyScoreAuditSummaryText(audit: StrategyScoreAuditSummary | null) {
  if (!audit) return '读取中';
  if (audit.overall_status === 'missing') return '暂无审计产物';
  return `${audit.anomaly_row_count} 条异常`;
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function strategyEvidenceMetrics(strategy: StrategyCatalogItem) {
  const evidence = strategy.latest_evidence || '';
  const navMatch = evidence.match(/净值(?:约)?\s*([0-9]+(?:\.[0-9]+)?)/);
  const drawdownMatch = evidence.match(/(?:最大)?回撤(?:约)?\s*(-?[0-9]+(?:\.[0-9]+)?)%/);
  const nav = navMatch ? Number(navMatch[1]) : null;
  const totalReturnPct =
    strategy.latest_metrics?.total_return_pct ??
    (typeof nav === 'number' && !Number.isNaN(nav) ? (nav - 1) * 100 : null);
  const maxDrawdownPct = strategy.latest_metrics?.max_drawdown_pct ?? (drawdownMatch ? Number(drawdownMatch[1]) : null);
  let status = 'Evidence';
  if (strategy.latest_metrics?.signal_status === 'strategy_failed') {
    status = 'NotReady';
  }
  if (typeof maxDrawdownPct === 'number' && !Number.isNaN(maxDrawdownPct)) {
    if (maxDrawdownPct <= -15) status = 'Review';
    else if (maxDrawdownPct <= -10) status = 'Caution';
    else status = 'Normal';
  }
  return {
    totalReturnPct,
    maxDrawdownPct,
    latestDayReturnPct: strategy.latest_metrics?.latest_day_return_pct ?? null,
    latestPeriodReturnPct: strategy.latest_metrics?.latest_period_return_pct ?? strategy.latest_metrics?.latest_day_return_pct ?? null,
    latestPeriodLabel: strategy.latest_metrics?.latest_period_label ?? '最近交易日',
    latestDayDrawdownPct: strategy.latest_metrics?.latest_day_drawdown_pct ?? null,
    asOfDate: strategy.latest_metrics?.as_of_date ?? null,
    signalStatus: strategy.latest_metrics?.signal_status ?? 'no_position_rows',
    signalCount: strategy.latest_metrics?.signal_count ?? null,
    status,
    evidence
  };
}

function activeStrategies(strategies: StrategyCatalogItem[]) {
  const byId = new Map(strategies.map((strategy) => [strategy.strategy_id, strategy]));
  return ACTIVE_STRATEGY_IDS.flatMap((strategyId) => {
    const strategy = byId.get(strategyId);
    return strategy ? [strategy] : [];
  });
}

function metricClass(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '';
  if (value > 0) return 'ashare-up-text';
  if (value < 0) return 'ashare-down-text';
  return '';
}

function signalLabel(metrics: ReturnType<typeof strategyEvidenceMetrics>) {
  if (metrics.signalStatus === 'strategy_failed') return '正式产物失败';
  if (typeof metrics.signalCount === 'number') {
    if (metrics.signalStatus === 'candidate_rows') return `当日候选 ${metrics.signalCount}`;
    if (metrics.signalStatus === 'current_holdings') return `当前持仓 ${metrics.signalCount}`;
    return `最新持仓 ${metrics.signalCount}`;
  }
  if (metrics.signalStatus === 'connected') return '最新持仓 0';
  if (metrics.signalStatus === 'candidate_rows') return '当日候选 0';
  if (metrics.signalStatus === 'current_holdings') return '当前持仓 0';
  return '持仓明细暂无';
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    Normal: '正常',
    Caution: '谨慎',
    Review: '复盘',
    Evidence: '待验证',
    NotReady: '未就绪'
  };
  return labels[status] ?? status;
}

function emotionComponentHint(key: string) {
  const labels: Record<string, string> = {
    breadth: '权重 25%：上涨/下跌比例 + 强涨/强跌比例',
    limit: '权重 25%：涨停数量加分，跌停和炸板率扣分',
    relay: '权重 20%：最高连板高度 + 二板以上占涨停比例',
    feedback: '权重 20%：昨日涨停、连板、炸板今天的收益反馈',
    liquidity: '权重 10%：5日成交额均值 / 20日成交额均值'
  };
  return labels[key] ?? '市场情绪子项评分';
}

function emotionComponentExplanation(key: string, marketMonitor: MarketMonitorPayload | null) {
  const emotion = marketMonitor?.market_emotion;
  if (!emotion) return '原始数据暂未接入。';
  const breadth = emotion.breadth;
  const limit = emotion.limit_performance;
  const profit = emotion.profit_effect;
  const liquidity = emotion.liquidity;
  if (key === 'breadth') {
    return `上涨 ${formatCount(breadth.up_count)}、下跌 ${formatCount(breadth.down_count)}，强涨 ${formatCount(breadth.strong_up_count)}、强跌 ${formatCount(breadth.strong_down_count)}。`;
  }
  if (key === 'limit') {
    return `涨停 ${formatCount(limit.limit_up_count)}、跌停 ${formatCount(limit.limit_down_count)}，炸板 ${formatCount(limit.broken_limit_up_count)}，炸板率 ${formatRatio(limit.broken_limit_up_rate)}。`;
  }
  if (key === 'relay') {
    return `二板 ${formatCount(limit.second_board_count)}、三板以上 ${formatCount(limit.third_board_plus_count)}，最高 ${formatCount(limit.high_board_height)} 板。`;
  }
  if (key === 'feedback') {
    return `昨日涨停红盘率 ${formatRatio(profit.limit_up_success_rate)}，连板晋级 ${formatRatio(profit.relay_continue_rate)}，炸板次日红盘率 ${formatRatio(profit.broken_success_rate)}。`;
  }
  if (key === 'liquidity') {
    return `5日/20日成交额比 ${formatRatio(liquidity.amount_ratio_5_20)}，总成交额 ${formatCount(liquidity.total_amount ? Math.round(liquidity.total_amount / 100000000) : null)} 亿。`;
  }
  return '该评分由市场情绪原始指标规则化计算。';
}

function marketEmotionFormulaReadout() {
  return '综合强度 = 涨跌广度25% + 涨停表现25% + 连板接力20% + 赚钱效应20% + 市场量能10%。';
}

function emotionComponentLabel(component: { key: string; label: string }) {
  const labels: Record<string, string> = {
    breadth: '涨跌广度评分',
    limit: '涨停表现评分',
    relay: '连板接力评分',
    feedback: '赚钱效应评分',
    liquidity: '市场量能评分'
  };
  return labels[component.key] ?? `${component.label}评分`;
}

function marketEmotionReadout(marketMonitor: MarketMonitorPayload | null) {
  const emotion = marketMonitor?.market_emotion;
  if (!emotion) return '市场情绪数据暂未接入。';
  const score = emotion.summary?.score;
  const state = formatState(emotion.summary?.state);
  const hint = formatState(emotion.summary?.position_budget_hint);
  const upCount = formatCount(emotion.breadth?.up_count);
  const downCount = formatCount(emotion.breadth?.down_count);
  const limitUp = formatCount(emotion.limit_performance?.limit_up_count);
  const broken = formatCount(emotion.limit_performance?.broken_limit_up_count);
  if (typeof score === 'number' && score >= 70) {
    return `情绪偏强但需要看炸板压力：上涨 ${upCount} 家、下跌 ${downCount} 家，涨停 ${limitUp} 家、炸板 ${broken} 家，仓位提示为${hint}。`;
  }
  if (typeof score === 'number' && score < 50) {
    return `情绪偏弱，优先关注回撤和流动性：上涨 ${upCount} 家、下跌 ${downCount} 家，仓位提示为${hint}。`;
  }
  return `市场情绪处于${state}区间，上涨 ${upCount} 家、下跌 ${downCount} 家，仓位提示为${hint}。`;
}

function stockNames(rows: MarketMonitorPayload['emotion_stock_lists']['limit_up']) {
  return rows.slice(0, 5).map((row) => row.name || row.symbol || row.asset_id).filter(Boolean);
}

export function HomeCockpit({ onNavigate }: HomeCockpitProps) {
  const [summary, setSummary] = useState<PlatformSummary | null>(null);
  const [strategies, setStrategies] = useState<StrategyCatalogItem[]>([]);
  const [marketMonitor, setMarketMonitor] = useState<MarketMonitorPayload | null>(null);
  const [marketMonitorLoading, setMarketMonitorLoading] = useState(true);
  const [newsItems, setNewsItems] = useState<PublicNewsItem[]>([]);
  const [readiness, setReadiness] = useState<PlatformReadiness | null>(null);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [scoreAudit, setScoreAudit] = useState<StrategyScoreAuditSummary | null>(null);
  const [widgetWarnings, setWidgetWarnings] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const visibleStrategies = activeStrategies(strategies);
  const baseDataHealth = healthGroup(readiness, 'base_data');
  const strategyHealth = healthGroup(readiness, 'strategy_execution');
  const reviewHealth = healthGroup(readiness, 'review_chain');
  const contentHealth = healthGroup(readiness, 'content_chain');
  const healthGroups = readiness?.health_groups ?? [];
  const displayTradeDate = readiness
    ? readiness.display_trade_date !== undefined
      ? readiness.display_trade_date || '-'
      : readiness.latest_trade_date ?? readiness.latest_market_date ?? '-'
    : summary?.latest_market_date ?? '-';

  useEffect(() => {
    let ignore = false;
    setIsLoading(true);
    setError(null);
    setWidgetWarnings([]);
    setMarketMonitor(null);
    setMarketMonitorLoading(true);
    setReadiness(null);
    setReadinessError(null);
    setScoreAudit(null);

    const addWidgetWarning = (warning: string) => {
      setWidgetWarnings((current) => [...current, warning]);
    };

    Promise.allSettled([
      fetchPlatformSummary(),
      fetchBacktestStrategies()
    ]).then(([summaryResult, strategiesResult]) => {
      if (ignore) return;

      const criticalErrors: string[] = [];

      if (summaryResult.status === 'fulfilled') {
        setSummary(summaryResult.value);
      } else {
        setSummary(null);
        criticalErrors.push(`平台摘要不可用：${errorMessage(summaryResult.reason)}`);
      }

      if (strategiesResult.status === 'fulfilled') {
        setStrategies(strategiesResult.value);
      } else {
        setStrategies([]);
        criticalErrors.push(`策略列表不可用：${errorMessage(strategiesResult.reason)}`);
      }

      setError(criticalErrors.length > 0 ? criticalErrors.join('; ') : null);
      setIsLoading(false);
    });

    void fetchMarketMonitorEod({ topN: 5 }).then(
      (marketPayload) => {
        if (!ignore) {
          setMarketMonitor(marketPayload);
          setMarketMonitorLoading(false);
        }
      },
      (err: unknown) => {
        if (!ignore) {
          setMarketMonitor(null);
          setMarketMonitorLoading(false);
          addWidgetWarning(`市场环境不可用：${errorMessage(err)}`);
        }
      }
    );

    void fetchPlatformReadiness().then(
      (payload) => {
        if (!ignore) {
          setReadiness(payload);
          setReadinessError(null);
        }
      },
      (err: unknown) => {
        if (!ignore) {
          setReadiness(null);
          setReadinessError(`平台就绪状态不可用：${errorMessage(err)}`);
        }
      }
    );

    void fetchPublicNews({ limit: 5, minQualityScore: 65 }).then(
      (newsPayload) => {
        if (!ignore) setNewsItems(newsPayload.items);
      },
      (err: unknown) => {
        if (!ignore) {
          setNewsItems([]);
          addWidgetWarning(`新闻流不可用：${errorMessage(err)}`);
        }
      }
    );

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!displayTradeDate || displayTradeDate === '-') {
      setScoreAudit(null);
      return;
    }

    let ignore = false;
    void fetchStrategyScoreAudit(displayTradeDate).then(
      (payload) => {
        if (!ignore) {
          setScoreAudit(payload);
        }
      },
      () => {
        if (!ignore) {
          setScoreAudit(null);
        }
      }
    );

    return () => {
      ignore = true;
    };
  }, [displayTradeDate]);

  return (
    <section className="home-cockpit" aria-label="策略指挥中心">
      <header className="workspace-header">
        <h1>策略指挥中心</h1>
        <p className="muted">围绕当前三条实盘研究策略，跟踪收益、回撤、最近交易日表现、市场环境和高质量新闻。</p>
      </header>

      {error ? <p className="error-text">{error}</p> : null}
      {widgetWarnings.map((warning) => (
        <p className="error-text" key={warning}>
          {warning}
        </p>
      ))}
      {readinessError ? <p className="error-text">{readinessError}</p> : null}

      <section className="status-strip command-status-strip" aria-label="首页状态">
        <div>
          <span>平台日期</span>
          <strong>{displayTradeDate}</strong>
        </div>
        <div>
          <span>数据健康</span>
          <strong className={`readiness-value ${readinessStatusClass(baseDataHealth?.status ?? readiness?.status)}`}>
            {baseDataHealth ? formatReadinessValue(baseDataHealth.status) : readiness ? formatReadinessValue(readiness.status) : '-'}
          </strong>
        </div>
        <div>
          <span>策略就绪</span>
          <strong>{readinessCount(strategyHealth, visibleStrategies.length || 3)}</strong>
        </div>
        <div>
          <span>复盘就绪</span>
          <strong>{readinessCount(reviewHealth, 3)}</strong>
        </div>
        <div>
          <span>风险状态</span>
          <strong className={`readiness-value ${readinessStatusClass(readiness?.status)}`}>{platformRiskStatus(readiness)}</strong>
        </div>
        <div className="status-strip-audit-cell">
          <span>策略打分审计</span>
          <strong className={`readiness-value ${strategyScoreAuditStatusClass(scoreAudit)}`}>
            {strategyScoreAuditStatusLabel(scoreAudit)}
          </strong>
          <small>{strategyScoreAuditSummaryText(scoreAudit)}</small>
        </div>
      </section>

      <section className="workspace-panel health-check-panel" aria-label="平台健康检查">
        <details>
          <summary>
            <span>健康检查</span>
            <strong>
              基础数据 {readinessCount(baseDataHealth, 4)} · 策略执行 {readinessCount(strategyHealth, 3)} · 复盘链路{' '}
              {readinessCount(reviewHealth, 3)} · 内容链路 {readinessCount(contentHealth, 3)}
            </strong>
          </summary>
          <div className="health-check-grid">
            {healthGroups.map((group) => (
              <article className="health-check-group" key={group.key}>
                <div className="health-check-group-header">
                  <strong>{group.label}</strong>
                  <span className={`health-status-pill ${readinessStatusClass(group.status)}`}>
                    {group.ready_count}/{group.total_count}
                  </span>
                </div>
                <div className="health-check-items">
                  {group.items.map((item) => (
                    <div className="health-check-item" key={item.key}>
                      <span className={`health-dot ${readinessStatusClass(item.status)}`} />
                      <div>
                        <strong>{item.label}</strong>
                        <small>{healthItemDetail(item)}</small>
                      </div>
                    </div>
                  ))}
                </div>
              </article>
            ))}
            {!healthGroups.length ? <p className="muted">健康检查数据加载中...</p> : null}
          </div>
        </details>
      </section>

      <section className="workspace-panel strategy-performance-panel" aria-label="启用策略表现">
        <div className="section-heading">
          <h2>启用策略表现</h2>
          {isLoading ? (
            <span className="muted">加载中...</span>
          ) : (
            <button type="button" onClick={() => onNavigate('strategyLab')}>
              打开策略实验室
            </button>
          )}
        </div>
        <div className="strategy-command-grid">
          {visibleStrategies.map((strategy) => {
            const metrics = strategyEvidenceMetrics(strategy);
            return (
              <article className="strategy-command-card" key={strategy.strategy_id}>
                <div className="strategy-command-card-header">
                  <strong>{strategy.strategy_name}</strong>
                  <span className="status-chip neutral">{statusLabel(metrics.status)}</span>
                </div>
                <div className="strategy-metric-grid">
                  <div>
                    <span>累计收益</span>
                    <strong className={metricClass(metrics.totalReturnPct)}>
                      {formatPercent(metrics.totalReturnPct, { signed: true })}
                    </strong>
                  </div>
                  <div>
                    <span>最大回撤</span>
                    <strong className={metricClass(metrics.maxDrawdownPct)}>{formatPercent(metrics.maxDrawdownPct)}</strong>
                  </div>
                  <div>
                    <span>{metrics.latestPeriodLabel}</span>
                    <strong className={metricClass(metrics.latestPeriodReturnPct)}>
                      {formatPercent(metrics.latestPeriodReturnPct, { signed: true })}
                    </strong>
                  </div>
                </div>
                <div className="strategy-card-footer">
                  <span>{metrics.asOfDate ? `截至 ${metrics.asOfDate}` : '最近日期未接入'}</span>
                  <span>{signalLabel(metrics)}</span>
                </div>
                <p>{metrics.evidence || strategy.description}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="cockpit-layout">
        <section className="workspace-panel strategy-position-panel" aria-label="策略持仓状态">
          <div className="section-heading">
            <h2>策略持仓状态</h2>
            <span className="status-chip neutral">非买卖建议</span>
          </div>
          <div className="strategy-signal-list">
            {visibleStrategies.map((strategy) => {
              const metrics = strategyEvidenceMetrics(strategy);
              return (
                <div className="strategy-signal-row" key={strategy.strategy_id}>
                  <strong>{strategy.strategy_name}</strong>
                  <span>{signalLabel(metrics)}</span>
                </div>
              );
            })}
          </div>
          <p className="muted">这里显示三条启用策略最新回测持仓数量；不作为买卖建议，具体股票名单放在策略实验室查看。</p>
        </section>

        <section className="workspace-panel market-regime-panel" aria-label="市场环境">
          <div className="section-heading">
            <h2>市场环境</h2>
            <span className="status-chip neutral">{formatState(marketMonitor?.market_emotion?.summary?.state)}</span>
          </div>
          {marketMonitorLoading ? (
            <div className="empty-state">
              <strong>市场环境加载中</strong>
              <p className="muted">正在读取最新可用交易日的市场情绪、涨跌家数和涨跌停结构。</p>
            </div>
          ) : (
            <>
          <div className="market-regime-grid">
            <div className="market-regime-card primary">
              <span>涨跌家数</span>
              <strong>
                {formatCount(marketMonitor?.market_emotion?.breadth?.up_count)} /{' '}
                {formatCount(marketMonitor?.market_emotion?.breadth?.down_count)}
              </strong>
              <small>上涨 / 下跌，强涨 {formatCount(marketMonitor?.market_emotion?.breadth?.strong_up_count)}，强跌 {formatCount(marketMonitor?.market_emotion?.breadth?.strong_down_count)}</small>
            </div>
            <div className="market-regime-card primary">
              <span>涨停 / 跌停</span>
              <strong>
                {formatCount(marketMonitor?.market_emotion?.limit_performance?.limit_up_count)} /{' '}
                {formatCount(marketMonitor?.market_emotion?.limit_performance?.limit_down_count)}
              </strong>
              <small>炸板 {formatCount(marketMonitor?.market_emotion?.limit_performance?.broken_limit_up_count)}，炸板率 {formatRatio(marketMonitor?.market_emotion?.limit_performance?.broken_limit_up_rate)}</small>
            </div>
            <div className="market-regime-card primary">
              <span>首板 / 二板</span>
              <strong>
                {formatCount(marketMonitor?.market_emotion?.limit_performance?.first_board_count)} /{' '}
                {formatCount(marketMonitor?.market_emotion?.limit_performance?.second_board_count)}
              </strong>
              <small>首板数量 / 二板数量</small>
            </div>
            <div className="market-regime-card primary">
              <span>三板以上 / 高度</span>
              <strong>
                {formatCount(marketMonitor?.market_emotion?.limit_performance?.third_board_plus_count)} /{' '}
                {formatCount(marketMonitor?.market_emotion?.limit_performance?.high_board_height)}
              </strong>
              <small>三板以上数量 / 最高连板高度</small>
            </div>
            <div className="market-regime-hero">
              <span>综合强度</span>
              <strong>{formatOneDecimal(marketMonitor?.market_emotion?.summary?.score)}</strong>
              <small>{formatState(marketMonitor?.market_emotion?.summary?.position_budget_hint)}</small>
            </div>
            <div className="market-regime-card">
              <span>连板数量</span>
              <div className="market-relay-split">
                <div>
                  <small>二板数量</small>
                  <strong>{formatCount(marketMonitor?.market_emotion?.limit_performance?.second_board_count)}</strong>
                </div>
                <div>
                  <small>三板以上</small>
                  <strong>{formatCount(marketMonitor?.market_emotion?.limit_performance?.third_board_plus_count)}</strong>
                </div>
              </div>
              <small>昨日涨停晋级 {formatRatio(marketMonitor?.market_emotion?.profit_effect?.relay_continue_rate)}</small>
            </div>
          </div>
          <div className="market-stock-preview-grid">
            <div>
              <span>涨停名单</span>
              <strong>
                {stockNames(marketMonitor?.emotion_stock_lists?.limit_up ?? []).join('、') || '股票列表未接入'}
              </strong>
            </div>
            <div>
              <span>跌停名单</span>
              <strong>
                {stockNames(marketMonitor?.emotion_stock_lists?.limit_down ?? []).join('、') || '股票列表未接入'}
              </strong>
            </div>
          </div>
          <div className="emotion-component-list" aria-label="市场情绪评分">
            {(marketMonitor?.market_emotion?.components ?? []).slice(0, 5).map((component) => (
              <div className="emotion-score-card" key={component.key}>
                <span>{emotionComponentLabel(component)}</span>
                <strong>{formatScore(component.score)}</strong>
                <small>{emotionComponentExplanation(component.key, marketMonitor)}</small>
                <em>{emotionComponentHint(component.key)}</em>
              </div>
            ))}
          </div>
          <p className="market-emotion-formula">{marketEmotionFormulaReadout()}</p>
          <p className="market-regime-readout">{marketEmotionReadout(marketMonitor)}</p>
            </>
          )}
        </section>

        <section className="workspace-panel quality-news-panel" aria-label="高质量新闻">
          <div className="section-heading">
            <h2>高质量新闻</h2>
            <button type="button" onClick={() => onNavigate('news')}>
              打开
            </button>
          </div>
          <ol className="quality-news-list">
            {newsItems.map((item, index) => (
              <li key={item.news_id}>
                <span>{index + 1}</span>
                <strong>{item.title}</strong>
              </li>
            ))}
          </ol>
        </section>
      </section>

      <section className="status-strip readiness-strip compact-readiness-strip" aria-label="平台就绪状态">
        <div>
          <span>就绪状态</span>
          <strong>{readiness ? formatReadinessValue(readiness.status) : '-'}</strong>
        </div>
        <div>
          <span>模式</span>
          <strong>{readiness ? formatMode(readiness.mode) : '-'}</strong>
        </div>
        <div>
          <span>警告数</span>
          <strong>{formatCount(readiness?.warnings.length)}</strong>
        </div>
        {(readiness?.warnings ?? []).map((warning) => (
          <div key={warning}>
            <span>警告</span>
            <strong className="warning-text">{formatReadinessWarning(warning)}</strong>
          </div>
        ))}
      </section>
    </section>
  );
}
