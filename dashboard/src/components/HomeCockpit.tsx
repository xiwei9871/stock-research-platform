import { useEffect, useState } from 'react';
import {
  fetchBacktestStrategies,
  fetchMarketMonitorEod,
  fetchPlatformReadiness,
  fetchPlatformSummary,
  fetchPublicNews
} from '../api/client';
import type {
  MarketMonitorPayload,
  PlatformReadiness,
  PlatformSummary,
  PublicNewsItem,
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
  | 'data'
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
    ready: '正常',
    partial: '部分可用',
    missing_data: '缺少数据',
    unknown: '未知'
  };
  const normalized = value.toLowerCase();
  return labels[normalized] ?? value;
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
    'Research Reports unavailable': '研报不可用',
    'Generated Reports unavailable': '生成报告不可用',
    'TopN preview unavailable': 'TopN 预览不可用'
  };
  return labels[value] ?? value;
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
  if (typeof maxDrawdownPct === 'number' && !Number.isNaN(maxDrawdownPct)) {
    if (maxDrawdownPct <= -15) status = 'Review';
    else if (maxDrawdownPct <= -10) status = 'Caution';
    else status = 'Normal';
  }
  return {
    totalReturnPct,
    maxDrawdownPct,
    latestDayReturnPct: strategy.latest_metrics?.latest_day_return_pct ?? null,
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
  if (typeof metrics.signalCount === 'number') return `最新持仓 ${metrics.signalCount}`;
  if (metrics.signalStatus === 'connected') return '最新持仓 0';
  return '持仓明细暂无';
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    Normal: '正常',
    Caution: '谨慎',
    Review: '复盘',
    Evidence: '待验证'
  };
  return labels[status] ?? status;
}

function emotionComponentHint(key: string) {
  const labels: Record<string, string> = {
    breadth: '上涨覆盖面和涨跌比例的综合评分，不是家数',
    limit: '涨停数量、封板质量和炸板压力的综合评分',
    relay: '连板晋级与昨日涨停接力表现评分',
    feedback: '打板成功率和次日收益表现评分',
    liquidity: '成交额相对近期均量的活跃度评分'
  };
  return labels[key] ?? '市场情绪子项评分';
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
  const [newsItems, setNewsItems] = useState<PublicNewsItem[]>([]);
  const [readiness, setReadiness] = useState<PlatformReadiness | null>(null);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [widgetWarnings, setWidgetWarnings] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const visibleStrategies = activeStrategies(strategies);

  useEffect(() => {
    let ignore = false;
    setIsLoading(true);
    setError(null);
    setWidgetWarnings([]);
    setReadiness(null);
    setReadinessError(null);

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
        if (!ignore) setMarketMonitor(marketPayload);
      },
      (err: unknown) => {
        if (!ignore) {
          setMarketMonitor(null);
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
          <span>市场日期</span>
          <strong>{summary?.latest_market_date ?? '-'}</strong>
        </div>
        <div>
          <span>因子日期</span>
          <strong>{summary?.latest_factor_date ?? '-'}</strong>
        </div>
        <div>
          <span>市场情绪日期</span>
          <strong>{marketMonitor?.trade_date || '-'}</strong>
        </div>
        <div>
          <span>启用策略</span>
          <strong>{formatCount(visibleStrategies.length)}</strong>
        </div>
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
                    <span>最近交易日</span>
                    <strong className={metricClass(metrics.latestDayReturnPct)}>
                      {formatPercent(metrics.latestDayReturnPct, { signed: true })}
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
                <small>{emotionComponentHint(component.key)}</small>
              </div>
            ))}
          </div>
          <p className="market-regime-readout">{marketEmotionReadout(marketMonitor)}</p>
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
