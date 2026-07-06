import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchAssetNews,
  fetchAssetProfile,
  fetchAssetResearchReports,
  fetchDailyBars,
  fetchEvidenceDigest,
  searchAssets,
  updateOperatorDecision
} from '../api/client';
import type {
  AssetNewsResponse,
  BarPoint,
  AssetProfile,
  AssetResearchReportResponse,
  AssetSummary,
  DecisionEventRow,
  EvidenceDigestResponse
} from '../api/types';
import { AssetChart } from '../charts/AssetChart';
import { OperatorDecisionPanel } from './OperatorDecisionPanel';
import type { SectorType } from './market-monitor/mockData';
import type { TechBottleneckStockEntryContext } from '../features/techBottleneckWatchlistReview/types';

const DEFAULT_ASSET_ID = '000001.SZ';
const DEFAULT_TRADE_DATE = '2026-06-18';
const SCORE_VERSION = 'manual_v1';
const ADJUST_TYPE = 'qfq';
const STOCK_CHART_VISIBLE_BARS = 120;
const DAILY_CHART_RESOLUTIONS = [
  { value: '1D', label: '日K' },
  { value: '1W', label: '周K' },
  { value: '1M', label: '月K' }
] as const;
const INTRADAY_CHART_RESOLUTIONS = [
  { value: '60m', label: '60m' },
  { value: '30m', label: '30m' },
  { value: '10m', label: '10m' },
  { value: '5m', label: '5m' }
] as const;
const CHART_RESOLUTIONS = [...DAILY_CHART_RESOLUTIONS, ...INTRADAY_CHART_RESOLUTIONS] as const;
type ChartResolution = (typeof CHART_RESOLUTIONS)[number]['value'];

type StockWorkspaceProps = {
  initialAssetId?: string;
  defaultTradeDate?: string;
  entryContext?: StockEntryContext;
  onOpenNews?: (context: StockEntryContext) => void;
  onOpenResearchReports?: (context: StockEntryContext) => void;
  onOpenMarketMonitor?: (context: StockEntryContext) => void;
};

function offsetDate(dateValue: string, dayOffset: number) {
  const date = new Date(`${dateValue}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + dayOffset);
  return date.toISOString().slice(0, 10);
}

type FactorDisplayRow = {
  group: string;
  name: string;
  value: unknown;
};

type StockWorkspaceAssetProfile = AssetProfile & {
  coverage: AssetProfile['coverage'] & {
    bars?: {
      end?: string | number;
    };
  };
};

export type StockEntryContext = {
  sourceWorkspace?: 'search' | 'news' | 'watchlist' | 'researchReports' | 'market' | 'reviewQueue' | 'techBottleneck';
  assetId?: string;
  query?: string;
  matchReason?: string;
  newsId?: string;
  eventKey?: string;
  reportId?: string;
  tradeDate?: string;
  monitorTab?: string;
  runId?: string;
  digestKey?: string;
  sourceType?: string;
  sourceName?: string;
  reviewItemSnapshotId?: string;
  evidenceDigestSnapshotId?: string;
  scoreVersion?: string;
  topnRank?: number | null;
} & TechBottleneckStockEntryContext;

function formatSourceWorkspace(sourceWorkspace: NonNullable<StockEntryContext['sourceWorkspace']>) {
  if (sourceWorkspace === 'search') return 'Search';
  if (sourceWorkspace === 'news') return 'News';
  if (sourceWorkspace === 'watchlist') return 'Watchlist';
  if (sourceWorkspace === 'researchReports') return 'Research Reports';
  if (sourceWorkspace === 'reviewQueue') return 'Review Queue';
  if (sourceWorkspace === 'techBottleneck') return 'Tech Bottleneck Candidate Review';
  return 'Market Monitor';
}

function formatDecisionLabel(label: string) {
  const normalized = label.toLowerCase();
  if (normalized === 'observe') return '观察';
  if (normalized === 'candidate') return '加入影子观察';
  if (normalized === 'no_action') return '跳过';
  if (normalized === 'caution') return '谨慎';
  if (normalized === 'remove') return '移除';
  return label;
}

function formatEvidenceBucket(bucket: string) {
  if (bucket === 'strong') return '证据较强';
  if (bucket === 'mixed') return '证据混合';
  if (bucket === 'risk_heavy') return '风险较多';
  if (bucket === 'thin') return '证据较薄';
  return bucket;
}

function formatSnapshotWarning(warning: string) {
  if (warning.includes('No review_item_snapshot lookup keys available')) {
    return '未找到复盘快照关联，本次决策仍会保存，但无法追溯到原始复盘队列快照。';
  }
  if (warning.includes('No evidence_digest_snapshot lookup keys available')) {
    return '未找到证据摘要快照关联，本次决策仍会保存，但证据摘要无法做完整追溯。';
  }
  return warning;
}

function normalizeAssetId(value: string) {
  const trimmed = value.trim().toUpperCase();
  if (/^\d{6}$/.test(trimmed)) {
    return `${trimmed}.${trimmed.startsWith('6') ? 'SH' : 'SZ'}`;
  }
  return trimmed;
}

function comparableStockCode(value: string) {
  const normalized = value.trim().toUpperCase();
  const sixDigitCode = normalized.match(/\d{6}/)?.[0];
  return sixDigitCode ?? normalized;
}

function isIntradayChartResolution(resolution: ChartResolution) {
  return INTRADAY_CHART_RESOLUTIONS.some((item) => item.value === resolution);
}

function toChartAxisPeriod(resolution: ChartResolution) {
  if (resolution === '1D' || resolution === '1W' || resolution === '1M') {
    return resolution;
  }
  return 'intraday';
}

function formatValue(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'boolean') {
    return value ? 'yes' : 'no';
  }
  if (value == null) {
    return '-';
  }
  return JSON.stringify(value);
}

function formatScore(profile: AssetProfile | null) {
  const score = profile?.score?.score_total;
  return typeof score === 'number' ? score.toFixed(1) : '-';
}

function formatDigestScore(score: number) {
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}

function getEvidenceDigestKey(assetId: string, date: string) {
  return `${assetId}|${date}`;
}

function getFactorRows(profile: AssetProfile | null): FactorDisplayRow[] {
  const rawFactorRows = (profile?.factor_values ?? []).map((row) => ({
    group: formatValue(row.factor_group ?? '-'),
    name: formatValue(row.factor_name ?? '-'),
    value: row.factor_value ?? '-'
  }));
  const scoreComponentRows = Object.entries(profile?.score?.score_components ?? {}).map(([name, value]) => ({
    group: 'Score Component',
    name,
    value
  }));
  return [...rawFactorRows, ...scoreComponentRows];
}

function formatReason(reason: Record<string, unknown>) {
  return Object.entries(reason)
    .map(([key, value]) => `${key}: ${formatValue(value)}`)
    .join(' / ');
}

function latestClose(profile: AssetProfile | null) {
  const bars = profile?.bars ?? [];
  const lastBar = bars.length > 0 ? bars[bars.length - 1] : null;
  return lastBar?.close ?? null;
}

function formatPercent(value: number | null) {
  if (value == null || Number.isNaN(value)) return '-';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatRatio(value: number | null) {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value.toFixed(2)}x`;
}

function formatPrice(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  return value.toFixed(2);
}

function formatPercentPoints(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function formatUnsignedPercentPoints(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value.toFixed(2)}%`;
}

function formatChineseAmount(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  const abs = Math.abs(value);
  if (abs >= 100000000) return `${(value / 100000000).toFixed(2)}亿`;
  if (abs >= 10000) return `${(value / 10000).toFixed(2)}万`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function formatTradeVolume(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(2)}万`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function formatOptionalMetric(value: number | null | undefined, formatter: (metric: number) => string) {
  if (value == null || Number.isNaN(value)) return '-';
  return formatter(value);
}

function formatResearchPriorityScore(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function formatReportScore(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  return value.toFixed(0);
}

function localReportHref(path?: string) {
  return path && path.trim() ? `/${path}` : '';
}

function pctChange(from: number | null | undefined, to: number | null | undefined) {
  if (!from || !to) return null;
  return to / from - 1;
}

function reviewPriceState(dayReturn: number | null, fiveDayReturn: number | null, highDrawdown: number | null) {
  if (highDrawdown != null && highDrawdown <= -0.08) return '回撤';
  if (dayReturn != null && dayReturn > 0.015 && fiveDayReturn != null && fiveDayReturn > 0.05) return '加速';
  if (fiveDayReturn != null && fiveDayReturn > 0.02) return '启动';
  if (fiveDayReturn != null && fiveDayReturn < -0.03) return '弱势';
  return '震荡';
}

function buildReviewMetrics(profile: AssetProfile | null) {
  const bars = profile?.bars ?? [];
  const last = bars.at(-1);
  const previous = bars.at(-2);
  const firstFive = bars.length >= 5 ? bars.at(-5) : bars[0];
  const firstTwenty = bars.length >= 20 ? bars.at(-20) : bars[0];
  const validAmounts = bars.map((bar) => bar.amount).filter((value): value is number => typeof value === 'number' && value > 0);
  const averageAmount =
    validAmounts.length > 0 ? validAmounts.reduce((sum, value) => sum + value, 0) / validAmounts.length : null;
  const latestAmount = typeof last?.amount === 'number' ? last.amount : null;
  const high = bars.reduce<number | null>((currentHigh, bar) => {
    if (typeof bar.high !== 'number') return currentHigh;
    return currentHigh == null ? bar.high : Math.max(currentHigh, bar.high);
  }, null);
  const highDrawdown = high && last?.close ? last.close / high - 1 : null;
  const dayReturn = pctChange(previous?.close, last?.close);
  const fiveDayReturn = pctChange(firstFive?.close, last?.close);
  const twentyDayReturn = pctChange(firstTwenty?.close, last?.close);
  const amountRatio = averageAmount && latestAmount ? latestAmount / averageAmount : null;

  return {
    dayReturn,
    fiveDayReturn,
    twentyDayReturn,
    amountRatio,
    highDrawdown,
    state: reviewPriceState(dayReturn, fiveDayReturn, highDrawdown)
  };
}

function buildFallbackQuoteSnapshot(profile: AssetProfile | null) {
  const bars = profile?.bars ?? [];
  const last = bars.at(-1);
  const previous = bars.at(-2);
  if (!last) return null;
  return {
    trade_date: last.time?.slice(0, 10) ?? null,
    open: last.open,
    high: last.high,
    low: last.low,
    close: last.close,
    preclose: previous?.close ?? null,
    volume: last.volume,
    amount: last.amount,
    turnover_rate: null,
    pct_chg:
      typeof previous?.close === 'number' && typeof last.close === 'number' && previous.close !== 0
        ? (last.close / previous.close - 1) * 100
        : null,
    amount_ratio_20d: buildReviewMetrics(profile).amountRatio,
    data_status: 'partial',
    missing_fields: ['turnover_rate', 'preclose']
  };
}

function lineageText(lineage: Record<string, unknown> | undefined, key: string) {
  const value = lineage?.[key];
  return typeof value === 'string' ? value : undefined;
}

export function StockWorkspace({
  initialAssetId = DEFAULT_ASSET_ID,
  defaultTradeDate = DEFAULT_TRADE_DATE,
  entryContext,
  onOpenNews,
  onOpenResearchReports,
  onOpenMarketMonitor
}: StockWorkspaceProps) {
  const initialTradeDate = entryContext?.tradeDate ?? defaultTradeDate ?? DEFAULT_TRADE_DATE;
  const initialStartDate = offsetDate(initialTradeDate, -180);
  const [assetId, setAssetId] = useState(initialAssetId);
  const [tradeDate, setTradeDate] = useState(initialTradeDate);
  const [startDate, setStartDate] = useState(initialStartDate);
  const [endDate, setEndDate] = useState(initialTradeDate);
  const [profile, setProfile] = useState<StockWorkspaceAssetProfile | null>(null);
  const [chartResolution, setChartResolution] = useState<ChartResolution>('1D');
  const [chartBars, setChartBars] = useState<BarPoint[]>([]);
  const [isChartLoading, setIsChartLoading] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);
  const [assetNews, setAssetNews] = useState<AssetNewsResponse | null>(null);
  const [researchReports, setResearchReports] = useState<AssetResearchReportResponse | null>(null);
  const [evidenceDigest, setEvidenceDigest] = useState<EvidenceDigestResponse | null>(null);
  const [assetMatches, setAssetMatches] = useState<AssetSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isNewsLoading, setIsNewsLoading] = useState(false);
  const [isResearchReportsLoading, setIsResearchReportsLoading] = useState(false);
  const [isEvidenceDigestLoading, setIsEvidenceDigestLoading] = useState(false);
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newsError, setNewsError] = useState<{ assetId: string; message: string } | null>(null);
  const [newsLoadingAssetId, setNewsLoadingAssetId] = useState<string | null>(null);
  const [researchReportsError, setResearchReportsError] = useState<string | null>(null);
  const [evidenceDigestError, setEvidenceDigestError] = useState<string | null>(null);
  const [evidenceDigestKey, setEvidenceDigestKey] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [editingDecisionId, setEditingDecisionId] = useState<string | null>(null);
  const [decisionEditNotes, setDecisionEditNotes] = useState('');
  const [decisionEditFollowUpNote, setDecisionEditFollowUpNote] = useState('');
  const [decisionEditRequiresFollowUp, setDecisionEditRequiresFollowUp] = useState(false);
  const [decisionEditSavingId, setDecisionEditSavingId] = useState<string | null>(null);
  const [decisionEditError, setDecisionEditError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const profileRequestIdRef = useRef(0);
  const newsRequestIdRef = useRef(0);
  const researchReportsRequestIdRef = useRef(0);
  const evidenceDigestRequestIdRef = useRef(0);
  const searchRequestIdRef = useRef(0);

  const isLatestProfileRequest = useCallback((requestId: number) => {
    return mountedRef.current && requestId === profileRequestIdRef.current;
  }, []);

  const loadAssetMatches = useCallback(async (query: string, profileRequestId: number) => {
    const requestId = searchRequestIdRef.current + 1;
    searchRequestIdRef.current = requestId;

    if (!query) {
      setAssetMatches([]);
      return;
    }

    setIsSearchLoading(true);
    setSearchError(null);

    try {
      const items = await searchAssets(query, 8);
      if (mountedRef.current && profileRequestId === profileRequestIdRef.current && requestId === searchRequestIdRef.current) {
        setAssetMatches(items);
      }
    } catch (err: unknown) {
      if (mountedRef.current && profileRequestId === profileRequestIdRef.current && requestId === searchRequestIdRef.current) {
        setSearchError(err instanceof Error ? err.message : String(err));
        setAssetMatches([]);
      }
    } finally {
      if (mountedRef.current && profileRequestId === profileRequestIdRef.current && requestId === searchRequestIdRef.current) {
        setIsSearchLoading(false);
      }
    }
  }, []);

  const loadProfile = useCallback(
    async (
      nextAssetId = assetId,
      nextTradeDate = tradeDate,
      nextStartDate = startDate,
      nextEndDate = endDate
    ) => {
      const requestId = profileRequestIdRef.current + 1;
      profileRequestIdRef.current = requestId;
      const normalizedAssetId = normalizeAssetId(nextAssetId);

      setIsLoading(true);
      setError(null);
      setNewsError(null);
      setAssetId(normalizedAssetId);

      try {
        const nextProfile = await fetchAssetProfile(
          normalizedAssetId,
          nextTradeDate,
          nextStartDate,
          nextEndDate,
          SCORE_VERSION,
          ADJUST_TYPE
        );
        if (!isLatestProfileRequest(requestId)) {
          return;
        }
        setProfile(nextProfile as StockWorkspaceAssetProfile);
        setChartBars(nextProfile.bars ?? []);
        void loadAssetMatches(normalizedAssetId, requestId);
      } catch (err: unknown) {
        if (!isLatestProfileRequest(requestId)) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        setProfile(null);
        setChartBars([]);
        setAssetMatches([]);
      } finally {
        if (isLatestProfileRequest(requestId)) {
          setIsLoading(false);
        }
      }
    },
    [assetId, endDate, isLatestProfileRequest, loadAssetMatches, startDate, tradeDate]
  );

  const startDecisionEdit = (decision: DecisionEventRow) => {
    setEditingDecisionId(decision.event_id);
    setDecisionEditNotes(decision.notes || '');
    setDecisionEditFollowUpNote(decision.follow_up_note || '');
    setDecisionEditRequiresFollowUp(decision.requires_follow_up);
    setDecisionEditError(null);
  };

  const cancelDecisionEdit = () => {
    setEditingDecisionId(null);
    setDecisionEditError(null);
  };

  const saveDecisionEdit = async (event: FormEvent<HTMLFormElement>, eventId: string) => {
    event.preventDefault();
    setDecisionEditSavingId(eventId);
    setDecisionEditError(null);
    try {
      const updated = await updateOperatorDecision(eventId, {
        notes: decisionEditNotes,
        requires_follow_up: decisionEditRequiresFollowUp,
        follow_up_note: decisionEditFollowUpNote
      });
      if (!mountedRef.current) {
        return;
      }
      setProfile((current) =>
        current
          ? {
              ...current,
              decisions: current.decisions.map((decision) =>
                decision.event_id === updated.event_id ? updated : decision
              )
            }
          : current
      );
      setEditingDecisionId(null);
    } catch (err: unknown) {
      if (mountedRef.current) {
        setDecisionEditError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (mountedRef.current) {
        setDecisionEditSavingId(null);
      }
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    setAssetId(normalizeAssetId(initialAssetId));
    setTradeDate(initialTradeDate);
    setStartDate(initialStartDate);
    setEndDate(initialTradeDate);
    void loadProfile(initialAssetId, initialTradeDate, initialStartDate, initialTradeDate);
    return () => {
      mountedRef.current = false;
      profileRequestIdRef.current += 1;
      newsRequestIdRef.current += 1;
      researchReportsRequestIdRef.current += 1;
      evidenceDigestRequestIdRef.current += 1;
      searchRequestIdRef.current += 1;
    };
  }, [initialAssetId, initialStartDate, initialTradeDate]);

  useEffect(() => {
    if (!profile?.canonical_asset_id) {
      newsRequestIdRef.current += 1;
      setAssetNews(null);
      setIsNewsLoading(false);
      setNewsLoadingAssetId(null);
      setNewsError(null);
      return;
    }

    const newsAssetId = profile.canonical_asset_id;
    const requestId = newsRequestIdRef.current + 1;
    newsRequestIdRef.current = requestId;

    setIsNewsLoading(true);
    setNewsLoadingAssetId(newsAssetId);
    setNewsError(null);
    setAssetNews(null);

    fetchAssetNews(newsAssetId, { limit: 8, lookbackDays: 7 })
      .then((payload) => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setAssetNews(payload);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setNewsError({ assetId: newsAssetId, message: err instanceof Error ? err.message : String(err) });
          setAssetNews(null);
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setIsNewsLoading(false);
          setNewsLoadingAssetId(null);
        }
      });
  }, [profile?.canonical_asset_id]);

  useEffect(() => {
    if (!profile) {
      setChartBars([]);
      setChartError(null);
      setIsChartLoading(false);
      return;
    }
    let ignore = false;
    setIsChartLoading(true);
    setChartError(null);
    const chartStartDate = isIntradayChartResolution(chartResolution) ? startDate : undefined;
    fetchDailyBars(profile.canonical_asset_id, chartStartDate, endDate, {
      resolution: chartResolution,
      adjustType: isIntradayChartResolution(chartResolution) ? 'raw' : ADJUST_TYPE
    })
      .then((rows) => {
        if (!ignore) {
          setChartBars(rows);
          setIsChartLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setChartBars([]);
          setChartError(err instanceof Error ? err.message : String(err));
          setIsChartLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [chartResolution, endDate, profile, startDate]);

  useEffect(() => {
    if (!profile) {
      researchReportsRequestIdRef.current += 1;
      setResearchReports(null);
      setIsResearchReportsLoading(false);
      setResearchReportsError(null);
      return;
    }

    const requestId = researchReportsRequestIdRef.current + 1;
    researchReportsRequestIdRef.current = requestId;

    setIsResearchReportsLoading(true);
    setResearchReportsError(null);
    setResearchReports(null);

    fetchAssetResearchReports(profile.canonical_asset_id, { limit: 5, lookbackDays: 90 })
      .then((payload) => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setResearchReports(payload);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setResearchReportsError(err instanceof Error ? err.message : String(err));
          setResearchReports(null);
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setIsResearchReportsLoading(false);
      }
    });
  }, [profile]);

  useEffect(() => {
    if (!profile) {
      evidenceDigestRequestIdRef.current += 1;
      setEvidenceDigest(null);
      setIsEvidenceDigestLoading(false);
      setEvidenceDigestError(null);
      setEvidenceDigestKey(null);
      return;
    }

    const digestAssetId = profile.canonical_asset_id;
    const digestKey = getEvidenceDigestKey(digestAssetId, tradeDate);
    const requestId = evidenceDigestRequestIdRef.current + 1;
    evidenceDigestRequestIdRef.current = requestId;

    setIsEvidenceDigestLoading(true);
    setEvidenceDigestError(null);
    setEvidenceDigestKey(digestKey);
    setEvidenceDigest(null);

    fetchEvidenceDigest(digestAssetId, { tradeDate, lookbackDays: 90 })
      .then((payload) => {
        if (mountedRef.current && requestId === evidenceDigestRequestIdRef.current) {
          setEvidenceDigest(payload);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === evidenceDigestRequestIdRef.current) {
          setEvidenceDigestError(err instanceof Error ? err.message : String(err));
          setEvidenceDigest(null);
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === evidenceDigestRequestIdRef.current) {
          setIsEvidenceDigestLoading(false);
        }
      });
  }, [profile]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void loadProfile();
  };

  const identityName = profile?.asset?.name ?? profile?.asset_id ?? assetId;
  const identitySymbol = profile?.asset?.symbol ?? profile?.asset_id ?? assetId;
  const factorRows = getFactorRows(profile);
  const close = latestClose(profile);
  const reviewMetrics = buildReviewMetrics(profile);
  const quoteSnapshot = profile?.quote_snapshot ?? buildFallbackQuoteSnapshot(profile);
  const companyProfile = profile?.company_profile;
  const valuationSnapshot = profile?.valuation_snapshot;
  const visibleAssetNews =
    assetNews && profile && assetNews.asset_id === profile.canonical_asset_id ? assetNews : null;
  const visibleNewsError =
    newsError && profile && newsError.assetId === profile.canonical_asset_id ? newsError.message : null;
  const isVisibleNewsLoading = Boolean(
    isNewsLoading && profile && newsLoadingAssetId === profile.canonical_asset_id
  );
  const visibleResearchReports =
    researchReports && profile && researchReports.asset_id === profile.canonical_asset_id ? researchReports : null;
  const latestNewsDate = visibleAssetNews?.summary.latest_published_at?.slice(0, 10) ?? '-';
  const latestReportDate = visibleResearchReports?.summary.latest_report_date ?? '-';
  const currentAssetId = profile?.canonical_asset_id ?? entryContext?.assetId ?? assetId;
  const entryContextAssetCode = entryContext?.assetId ? comparableStockCode(entryContext.assetId) : null;
  const currentAssetCode = comparableStockCode(currentAssetId);
  const isEntryContextForCurrentAsset = !entryContextAssetCode || entryContextAssetCode === currentAssetCode;
  const currentEntryContext: StockEntryContext = isEntryContextForCurrentAsset
    ? {
        ...entryContext,
        assetId: currentAssetId,
        query: entryContext?.query ?? profile?.asset?.symbol ?? profile?.canonical_asset_id ?? assetId
      }
    : {
        assetId: currentAssetId
      };
  const sourceObjectIds = [
    currentEntryContext.newsId ? `newsId: ${currentEntryContext.newsId}` : null,
    currentEntryContext.eventKey ? `eventKey: ${currentEntryContext.eventKey}` : null,
    currentEntryContext.reportId ? `reportId: ${currentEntryContext.reportId}` : null,
    currentEntryContext.tradeDate ? `Trade Date ${currentEntryContext.tradeDate}` : null,
    currentEntryContext.monitorTab ? `Monitor Tab ${currentEntryContext.monitorTab}` : null,
    currentEntryContext.techBottleneckSource ? `Tech Bottleneck Source ${currentEntryContext.techBottleneckSource}` : null
  ].filter((value): value is string => Boolean(value));
  const isTechBottleneckEntry = currentEntryContext.sourceWorkspace === 'techBottleneck';
  const visibleEvidenceDigest =
    evidenceDigest &&
    profile &&
    evidenceDigest.canonical_asset_id === profile.canonical_asset_id &&
    evidenceDigest.trade_date === tradeDate
      ? evidenceDigest
      : null;
  const expectedEvidenceDigestKey = profile ? getEvidenceDigestKey(profile.canonical_asset_id, tradeDate) : null;
  const isEvidenceDigestPending =
    Boolean(expectedEvidenceDigestKey) && (isEvidenceDigestLoading || evidenceDigestKey !== expectedEvidenceDigestKey);
  const digestLineage = visibleEvidenceDigest?.lineage;
  const decisionRunId = visibleEvidenceDigest?.run_id ?? currentEntryContext.runId;
  const decisionDigestKey = visibleEvidenceDigest?.digest_key ?? currentEntryContext.digestKey;
  const decisionSourceType = lineageText(digestLineage, 'source_type') ?? currentEntryContext.sourceType;
  const decisionSourceName = lineageText(digestLineage, 'source_name') ?? currentEntryContext.sourceName;
  const decisionReviewItemSnapshotId =
    lineageText(digestLineage, 'review_item_snapshot_id') ?? currentEntryContext.reviewItemSnapshotId;
  const decisionEvidenceDigestSnapshotId =
    lineageText(digestLineage, 'evidence_digest_snapshot_id') ?? currentEntryContext.evidenceDigestSnapshotId;
  const reviewSourceName = currentEntryContext.sourceName ?? decisionSourceName ?? currentEntryContext.sourceWorkspace;
  const reviewRank = currentEntryContext.topnRank ?? profile?.score?.rank ?? null;
  const marketMonitorSection = visibleEvidenceDigest?.sections?.market_monitor;
  const marketMonitorStatus = marketMonitorSection?.status ?? 'missing';
  const marketMonitorTab = visibleEvidenceDigest?.source_refs.monitor_tab ?? currentEntryContext.monitorTab ?? '';
  const marketFacts = visibleEvidenceDigest?.facts.filter((fact) => fact.kind === 'market') ?? [];
  const marketRiskFlags =
    visibleEvidenceDigest?.risk_flags.filter((flag) => flag.key.startsWith('market_')) ?? [];
  const isIntradayChartActive = isIntradayChartResolution(chartResolution);
  const chartAxisPeriod = toChartAxisPeriod(chartResolution);
  const visibleChartBarCount = chartBars.length > 0 ? Math.min(STOCK_CHART_VISIBLE_BARS, chartBars.length) : STOCK_CHART_VISIBLE_BARS;
  const chartWindowLabel = isIntradayChartActive
    ? `${startDate} to ${endDate}`
    : `历史 ${chartBars.length} bars / 固定显示 ${visibleChartBarCount} bars / 截至 ${endDate}`;

  return (
    <section className="workspace-stack stock-detail-shell" aria-label="Stock Workspace workspace">
      <header className="workspace-header">
        <h1>{profile ? `${identityName} ${profile.canonical_asset_id}` : 'Stock Workspace'}</h1>
        <p className="muted">个股复盘工作台：集中查看走势、策略证据、新闻研报和人工复盘记录。</p>
        {currentEntryContext.sourceWorkspace ? (
          <p className="muted">
            Opened from {formatSourceWorkspace(currentEntryContext.sourceWorkspace)}
            {currentEntryContext.matchReason ? (
              <>
                {' '}
                <span>{currentEntryContext.matchReason}</span>
              </>
            ) : null}
          </p>
        ) : null}
        {sourceObjectIds.length > 0 ? (
          <div className="tag-stack" aria-label="Source context">
            {sourceObjectIds.map((sourceObjectId) => (
              <span key={sourceObjectId} className="status-chip neutral">
                {sourceObjectId}
              </span>
            ))}
          </div>
        ) : null}
      </header>

      {isTechBottleneckEntry ? (
        <section className="workspace-band tech-bottleneck-stock-context" role="region" aria-label="技术瓶颈候选上下文">
          <div className="section-heading">
            <div>
              <h2>技术瓶颈候选上下文</h2>
              <p className="muted">Research-only · manual review only · no production signal/admission</p>
            </div>
            <span className="status-chip neutral">{currentEntryContext.reviewStatus ?? 'not_reviewed'}</span>
          </div>
          <div className="stock-summary-strip compact tech-bottleneck-context-metrics">
            <div>
              <span>候选名称</span>
              <strong>{currentEntryContext.stockName ?? currentEntryContext.query ?? currentAssetId}</strong>
            </div>
            <div>
              <span>来源</span>
              <strong>{currentEntryContext.sourceGroup ?? '-'}</strong>
            </div>
            <div>
              <span>原 Tier</span>
              <strong>{currentEntryContext.previousTier ?? '-'}</strong>
            </div>
            <div>
              <span>证据强度</span>
              <strong>{currentEntryContext.evidenceStrength ?? '-'}</strong>
            </div>
            <div>
              <span>瓶颈相关性</span>
              <strong>{currentEntryContext.bottleneckRelevance ?? '-'}</strong>
            </div>
            <div>
              <span>研究优先级</span>
              <strong>{formatResearchPriorityScore(currentEntryContext.researchPriorityScore)}</strong>
            </div>
          </div>
          <div className="tech-bottleneck-context-grid">
            <article>
              <span>人工审批分类</span>
              <strong>{currentEntryContext.finalManualApprovalCategory ?? '-'}</strong>
            </article>
            <article>
              <span>证据/业务类别</span>
              <strong>{currentEntryContext.evidenceCategory || currentEntryContext.businessRelevanceCategory || '-'}</strong>
            </article>
            <article>
              <span>下一步动作</span>
              <strong>{currentEntryContext.nextAction ?? '-'}</strong>
            </article>
            <article>
              <span>Guardrails</span>
              <strong>allowed_for_signal={currentEntryContext.allowedForSignal ? 'true' : 'false'}</strong>
              <strong>allowed_for_admission={currentEntryContext.allowedForAdmission ? 'true' : 'false'}</strong>
            </article>
          </div>
          {currentEntryContext.rationale ? <p>{currentEntryContext.rationale}</p> : null}
          {currentEntryContext.evidenceExcerpt ? <p className="muted">{currentEntryContext.evidenceExcerpt}</p> : null}
          {currentEntryContext.primarySourceUrl ? (
            <a href={currentEntryContext.primarySourceUrl} target="_blank" rel="noreferrer">
              打开 primary source
            </a>
          ) : null}
        </section>
      ) : null}

      {isTechBottleneckEntry ? (
        <section className="workspace-band tech-bottleneck-report-panel" role="region" aria-label="Tech Bottleneck Report panel">
          <div className="section-heading">
            <div>
              <h2>Tech Bottleneck Report</h2>
              <p className="muted">Enriched source-backed report access · research-only</p>
            </div>
            <span className="status-chip neutral">{currentEntryContext.reportStatus ?? 'report_pending'}</span>
          </div>
          <div className="stock-summary-strip compact tech-bottleneck-context-metrics">
            <div>
              <span>report_status</span>
              <strong>{currentEntryContext.reportStatus ?? '-'}</strong>
            </div>
            <div>
              <span>bottleneck_confidence_score</span>
              <strong>{formatReportScore(currentEntryContext.bottleneckConfidenceScore)}</strong>
            </div>
            <div>
              <span>evidence_quality_score</span>
              <strong>{formatReportScore(currentEntryContext.evidenceQualityScore)}</strong>
            </div>
            <div>
              <span>review_decision</span>
              <strong>{currentEntryContext.reportReviewDecision ?? '-'}</strong>
            </div>
            <div>
              <span>evidence_strength</span>
              <strong>{currentEntryContext.evidenceStrength ?? '-'}</strong>
            </div>
            <div>
              <span>bottleneck_relevance</span>
              <strong>{currentEntryContext.bottleneckRelevance ?? '-'}</strong>
            </div>
          </div>
          <div className="tech-bottleneck-report-links" aria-label="Tech Bottleneck report links">
            {currentEntryContext.reportHtmlPath ? (
              <a href={localReportHref(currentEntryContext.reportHtmlPath)} target="_blank" rel="noreferrer">
                打开HTML报告
              </a>
            ) : null}
            {currentEntryContext.reportPdfPath ? (
              <a href={localReportHref(currentEntryContext.reportPdfPath)} target="_blank" rel="noreferrer">
                打开PDF报告
              </a>
            ) : null}
            {currentEntryContext.evidenceMatrixPath ? (
              <a href={localReportHref(currentEntryContext.evidenceMatrixPath)} target="_blank" rel="noreferrer">
                查看证据矩阵
              </a>
            ) : null}
            {currentEntryContext.reportSourcesPath ? (
              <a href={localReportHref(currentEntryContext.reportSourcesPath)} target="_blank" rel="noreferrer">
                查看引用与数据源
              </a>
            ) : null}
          </div>
          <div className="tech-bottleneck-context-grid">
            <article>
              <span>evidence_gap_note</span>
              <strong>{currentEntryContext.evidenceGapNote ?? '-'}</strong>
            </article>
            <article>
              <span>next_action</span>
              <strong>{currentEntryContext.nextAction ?? '-'}</strong>
            </article>
          </div>
        </section>
      ) : null}

      <details className="stock-load-settings">
        <summary>
          <span>回放 / 切换设置</span>
          <small>
            {assetId} · 复盘日 {tradeDate} · 图表 {startDate} 至 {endDate}
          </small>
        </summary>
        <form className="compact-toolbar" onSubmit={handleSubmit}>
          <label>
            股票代码
            <input
              aria-label="stock workspace asset"
              value={assetId}
              onChange={(event) => setAssetId(event.target.value)}
            />
          </label>
          <label>
            复盘日期
            <input
              aria-label="stock workspace trade date"
              type="date"
              value={tradeDate}
              onChange={(event) => setTradeDate(event.target.value)}
            />
          </label>
          <label>
            图表开始
            <input
              aria-label="stock workspace start date"
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </label>
          <label>
            图表结束
            <input
              aria-label="stock workspace end date"
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </label>
          <button type="submit">加载回放</button>
          {isLoading ? <span className="muted">正在加载...</span> : null}
        </form>
      </details>

      {error ? <p className="error-text">{error}</p> : null}

      {profile ? (
        <>
          <section className="workspace-band stock-quote-dossier" role="region" aria-label="行情快照">
            <div className="section-heading">
              <div>
                <h2>行情快照</h2>
                <p className="muted">
                  {quoteSnapshot?.trade_date ?? endDate} · 数据状态 {quoteSnapshot?.data_status ?? 'missing'}
                </p>
              </div>
              <span
                className={
                  quoteSnapshot?.pct_chg != null && quoteSnapshot.pct_chg < 0
                    ? 'status-chip market-down'
                    : 'status-chip market-up'
                }
              >
                {formatPercentPoints(quoteSnapshot?.pct_chg)}
              </span>
            </div>
            <div className="stock-dossier-grid">
              <div className="stock-summary-strip stock-quote-metrics">
                <div>
                  <span>最新价</span>
                  <strong className={quoteSnapshot?.pct_chg != null && quoteSnapshot.pct_chg < 0 ? 'market-down' : 'market-up'}>
                    {formatPrice(quoteSnapshot?.close)}
                  </strong>
                </div>
                <div>
                  <span>涨跌幅</span>
                  <strong className={quoteSnapshot?.pct_chg != null && quoteSnapshot.pct_chg < 0 ? 'market-down' : 'market-up'}>
                    {formatPercentPoints(quoteSnapshot?.pct_chg)}
                  </strong>
                </div>
                <div>
                  <span>今开</span>
                  <strong>{formatPrice(quoteSnapshot?.open)}</strong>
                </div>
                <div>
                  <span>最高</span>
                  <strong>{formatPrice(quoteSnapshot?.high)}</strong>
                </div>
                <div>
                  <span>最低</span>
                  <strong>{formatPrice(quoteSnapshot?.low)}</strong>
                </div>
                <div>
                  <span>昨收</span>
                  <strong>{formatPrice(quoteSnapshot?.preclose)}</strong>
                </div>
                <div>
                  <span>成交量</span>
                  <strong>{formatTradeVolume(quoteSnapshot?.volume)}</strong>
                </div>
                <div>
                  <span>成交额</span>
                  <strong>{formatChineseAmount(quoteSnapshot?.amount)}</strong>
                </div>
                <div>
                  <span>换手率</span>
                  <strong>{formatUnsignedPercentPoints(quoteSnapshot?.turnover_rate)}</strong>
                </div>
                <div>
                  <span>量能/20日均额</span>
                  <strong>{formatRatio(quoteSnapshot?.amount_ratio_20d ?? null)}</strong>
                </div>
              </div>
            </div>
            <div className="stock-dossier-support">
              <article className="stock-mini-panel" role="region" aria-label="规模估值">
                <div className="section-heading compact-heading">
                  <h3>规模估值</h3>
                  <span className="muted">{valuationSnapshot?.data_status ?? 'unavailable'}</span>
                </div>
                <div className="stock-summary-strip compact">
                  <div>
                    <span>总市值</span>
                    <strong>{formatOptionalMetric(valuationSnapshot?.total_market_cap, formatChineseAmount)}</strong>
                  </div>
                  <div>
                    <span>流通市值</span>
                    <strong>{formatOptionalMetric(valuationSnapshot?.float_market_cap, formatChineseAmount)}</strong>
                  </div>
                  <div>
                    <span>市盈率</span>
                    <strong>{formatOptionalMetric(valuationSnapshot?.pe_ttm, (value) => value.toFixed(2))}</strong>
                  </div>
                  <div>
                    <span>PB</span>
                    <strong>{formatOptionalMetric(valuationSnapshot?.pb, (value) => value.toFixed(2))}</strong>
                  </div>
                  <div>
                    <span>量比</span>
                    <strong>{formatOptionalMetric(valuationSnapshot?.volume_ratio, (value) => `${value.toFixed(2)}x`)}</strong>
                  </div>
                </div>
              </article>
              <article className="stock-mini-panel" role="region" aria-label="股票简况">
                <div className="section-heading compact-heading">
                  <h3>股票简况</h3>
                  <span className="muted">{companyProfile?.source ?? 'asset detail'}</span>
                </div>
                <div className="stock-summary-strip compact">
                  <div>
                    <span>交易所</span>
                    <strong>{companyProfile?.exchange ?? profile.asset?.exchange ?? '-'}</strong>
                  </div>
                  <div>
                    <span>板块</span>
                    <strong>{companyProfile?.board ?? profile.asset?.board ?? '-'}</strong>
                  </div>
                  <div>
                    <span>上市日期</span>
                    <strong>{companyProfile?.list_date ?? '-'}</strong>
                  </div>
                  <div>
                    <span>区域</span>
                    <strong>{companyProfile?.region ?? '-'}</strong>
                  </div>
                  <div>
                    <span>状态</span>
                    <strong>{companyProfile?.is_active ?? profile.asset?.is_active ? '正常' : '非活跃'}</strong>
                  </div>
                </div>
              </article>
            </div>
          </section>

          <section className="workspace-band stock-review-summary" role="region" aria-label="复盘摘要">
            <div className="section-heading">
              <div>
                <h2>策略复盘摘要</h2>
                <strong className="stock-review-name">{identityName}</strong>
                <p className="muted">
                  {profile.canonical_asset_id} · {identitySymbol}
                </p>
              </div>
              <span className="status-chip">{reviewMetrics.state}</span>
            </div>
            <div className="stock-summary-strip stock-review-metrics">
              <div>
                <span>来源策略</span>
                <strong>{reviewSourceName ?? '-'}</strong>
              </div>
              <div>
                <span>复盘日期</span>
                <strong>{tradeDate}</strong>
              </div>
              <div>
                <span>策略排名</span>
                <strong>{reviewRank != null ? `第 ${reviewRank} 名` : '-'}</strong>
              </div>
              <div>
                <span>策略分数</span>
                <strong>{formatScore(profile)}</strong>
              </div>
              <div>
                <span>最新收盘</span>
                <strong>{formatValue(close)}</strong>
              </div>
              <div>
                <span>当日涨跌幅</span>
                <strong className={reviewMetrics.dayReturn != null && reviewMetrics.dayReturn < 0 ? 'market-down' : 'market-up'}>
                  {formatPercent(reviewMetrics.dayReturn)}
                </strong>
              </div>
              <div>
                <span>近5日表现</span>
                <strong className={reviewMetrics.fiveDayReturn != null && reviewMetrics.fiveDayReturn < 0 ? 'market-down' : 'market-up'}>
                  {formatPercent(reviewMetrics.fiveDayReturn)}
                </strong>
              </div>
              <div>
                <span>近20日表现</span>
                <strong className={reviewMetrics.twentyDayReturn != null && reviewMetrics.twentyDayReturn < 0 ? 'market-down' : 'market-up'}>
                  {formatPercent(reviewMetrics.twentyDayReturn)}
                </strong>
              </div>
              <div>
                <span>量能/20日均额</span>
                <strong>{formatRatio(reviewMetrics.amountRatio)}</strong>
              </div>
              <div>
                <span>高位回撤</span>
                <strong className={reviewMetrics.highDrawdown != null && reviewMetrics.highDrawdown < 0 ? 'market-down' : 'market-up'}>
                  {formatPercent(reviewMetrics.highDrawdown)}
                </strong>
              </div>
              <div>
                <span>价格状态</span>
                <strong>{reviewMetrics.state}</strong>
              </div>
              <div>
                <span>新闻/研报</span>
                <strong>
                  {visibleAssetNews?.summary.news_count_7d ?? '-'} / {latestReportDate}
                </strong>
              </div>
            </div>
          </section>

          <div className="stock-detail-layout">
            <aside className="workspace-band stock-context-rail" role="region" aria-label="复盘决策栏">
              <div className="section-heading">
                <h2>复盘操作</h2>
                <span className="muted">{profile.canonical_asset_id}</span>
              </div>
              <OperatorDecisionPanel
                assetId={profile.canonical_asset_id}
                stockCode={visibleEvidenceDigest?.stock_code ?? profile.canonical_asset_id}
                stockName={visibleEvidenceDigest?.stock_name ?? profile.asset?.name}
                decisionDate={visibleEvidenceDigest?.latest_trade_date ?? visibleEvidenceDigest?.trade_date ?? tradeDate}
                runId={decisionRunId}
                digestKey={decisionDigestKey}
                reviewItemSnapshotId={decisionReviewItemSnapshotId}
                evidenceDigestSnapshotId={decisionEvidenceDigestSnapshotId}
                sourceType={decisionSourceType}
                sourceName={decisionSourceName}
                sourceContextEntry="evidence_digest"
                onDecisionCreated={() => {
                  void loadProfile(currentAssetId, tradeDate, startDate, endDate);
                }}
              />
              <section className="stock-review-log" role="region" aria-label="复盘日志">
                <div className="section-heading compact-heading">
                  <h3>复盘日志</h3>
                  <span className="muted">{profile.decisions.length} 条</span>
                </div>
                {decisionEditError ? <p className="error-text">{decisionEditError}</p> : null}
                <div className="decision-list">
                  {profile.decisions.map((decision) => {
                    const isEditing = editingDecisionId === decision.event_id;
                    return (
                      <article className="decision-row" key={decision.event_id}>
                        <div>
                          <strong>{formatDecisionLabel(decision.decision_label)}</strong>
                          <span>{decision.review_date}</span>
                        </div>
                        {isEditing ? (
                          <form className="workspace-stack" onSubmit={(event) => saveDecisionEdit(event, decision.event_id)}>
                            <label>
                              复盘备注
                              <textarea
                                aria-label="复盘日志备注"
                                rows={3}
                                value={decisionEditNotes}
                                onChange={(event) => setDecisionEditNotes(event.target.value)}
                              />
                            </label>
                            <label className="inline-check">
                              <input
                                aria-label="需要跟进"
                                type="checkbox"
                                checked={decisionEditRequiresFollowUp}
                                onChange={(event) => setDecisionEditRequiresFollowUp(event.target.checked)}
                              />
                              需要跟进
                            </label>
                            <label>
                              跟进说明
                              <input
                                aria-label="跟进说明"
                                value={decisionEditFollowUpNote}
                                onChange={(event) => setDecisionEditFollowUpNote(event.target.value)}
                              />
                            </label>
                            <div className="compact-toolbar">
                              <button type="submit" disabled={decisionEditSavingId === decision.event_id}>
                                {decisionEditSavingId === decision.event_id ? '保存中...' : '保存复盘日志'}
                              </button>
                              <button type="button" onClick={cancelDecisionEdit}>
                                取消
                              </button>
                            </div>
                          </form>
                        ) : (
                          <>
                            <p>{decision.notes || '暂无备注'}</p>
                            {decision.follow_up_note ? <span>{decision.follow_up_note}</span> : null}
                            {decision.requires_follow_up ? <span className="risk-tag">需要跟进</span> : null}
                            <button type="button" className="inline-button" onClick={() => startDecisionEdit(decision)}>
                              编辑复盘日志
                            </button>
                          </>
                        )}
                      </article>
                    );
                  })}
                </div>
                {profile.decisions.length === 0 ? <p className="muted">暂无复盘日志，保存一次复盘决策后会出现在这里。</p> : null}
              </section>
              <div className="section-heading compact-heading">
                <h3>外部证据入口</h3>
              </div>
              <div className="compact-toolbar">
                <button type="button" aria-label="Open News workspace" onClick={() => onOpenNews?.(currentEntryContext)}>
                  打开新闻
                </button>
                <button
                  type="button"
                  aria-label="Open Research Reports workspace"
                  onClick={() => onOpenResearchReports?.(currentEntryContext)}
                >
                  打开研报
                </button>
              </div>
            </aside>

            <div className="stock-detail-main">
              <section className="workspace-band" role="region" aria-label="Evidence Digest">
                <div className="section-heading">
                  <h2>Evidence Digest</h2>
                  {isEvidenceDigestPending ? <span className="muted">Loading digest...</span> : null}
                </div>
                {evidenceDigestError ? <p className="error-text">{evidenceDigestError}</p> : null}
                {visibleEvidenceDigest ? (
                  <>
                    <div className="metric-grid compact">
                      <span>
                        <span>Title</span>
                        <strong>{visibleEvidenceDigest.title}</strong>
                      </span>
                      <span>
                        <span>Score</span>
                        <strong>Score {formatDigestScore(visibleEvidenceDigest.score)}</strong>
                      </span>
                      <span>
                        <span>Bucket</span>
                        <strong>{formatEvidenceBucket(visibleEvidenceDigest.bucket)}</strong>
                      </span>
                    </div>
                    <div className="compact-news-list">
                      {visibleEvidenceDigest.facts.map((fact) => (
                        <div key={`${fact.kind}-${fact.key ?? fact.label}`} className="news-stock-row">
                          <strong>{fact.label}</strong>
                          {fact.severity ? <span className="status-chip neutral">{fact.severity}</span> : null}
                        </div>
                      ))}
                    </div>
                    {visibleEvidenceDigest.risk_flags.length > 0 ? (
                      <div className="tag-stack">
                        {visibleEvidenceDigest.risk_flags.map((flag) => (
                          <span key={flag.key} className="status-chip warning">
                            {flag.label}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {visibleEvidenceDigest.warnings.length > 0 ? (
                      <div className="tag-stack">
                        {visibleEvidenceDigest.warnings.map((warning) => (
                          <span className="status-chip neutral" key={warning}>
                            {formatSnapshotWarning(warning)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : null}
                {!isEvidenceDigestPending && !evidenceDigestError && !visibleEvidenceDigest ? (
                  <p className="muted">No digest available.</p>
                ) : null}
              </section>

              <section className="workspace-band" aria-label="Price & Events">
                <div className="section-heading">
                  <h2>价格走势</h2>
                  <span className="muted">
                    {isIntradayChartActive ? `${chartBars.length} bars / ` : ''}
                    {chartWindowLabel}
                  </span>
                </div>
                <div className="segmented-control stock-chart-resolution" role="group" aria-label="K line period">
                  {DAILY_CHART_RESOLUTIONS.map((resolution) => (
                    <button
                      key={resolution.value}
                      type="button"
                      className={chartResolution === resolution.value ? 'active' : ''}
                      aria-pressed={chartResolution === resolution.value}
                      onClick={() => setChartResolution(resolution.value)}
                    >
                      {resolution.label}
                    </button>
                  ))}
                  <button
                    type="button"
                    className={isIntradayChartActive ? 'active' : ''}
                    aria-pressed={isIntradayChartActive}
                    onClick={() => setChartResolution(isIntradayChartActive ? chartResolution : '60m')}
                  >
                    分时
                  </button>
                </div>
                {isIntradayChartActive ? (
                  <div className="segmented-control stock-chart-resolution stock-chart-intraday-resolution" role="group" aria-label="分时周期">
                    {INTRADAY_CHART_RESOLUTIONS.map((resolution) => (
                      <button
                        key={resolution.value}
                        type="button"
                        className={chartResolution === resolution.value ? 'active' : ''}
                        aria-pressed={chartResolution === resolution.value}
                        onClick={() => setChartResolution(resolution.value)}
                      >
                        {resolution.label}
                      </button>
                    ))}
                  </div>
                ) : null}
                {isChartLoading ? <p className="muted">Loading chart bars...</p> : null}
                {chartError ? <p className="error-text">{chartError}</p> : null}
                {!isChartLoading && chartBars.length > 0 ? (
                  <AssetChart
                    bars={chartBars}
                    timeAxisMode={isIntradayChartActive ? 'intraday' : 'daily'}
                    timeAxisPeriod={chartAxisPeriod}
                    visibleBarCount={STOCK_CHART_VISIBLE_BARS}
                  />
                ) : null}
                {!isChartLoading && !chartError && chartBars.length === 0 ? <p className="muted">No bars available.</p> : null}
              </section>

              <section className="stock-evidence-grid">
            <article className="workspace-band" role="region" aria-label="Market Monitor State">
              <div className="section-heading">
                <h2>个股市场环境</h2>
                <span className="muted">{marketMonitorStatus}</span>
              </div>
              <div className="stock-summary-strip stock-review-metrics">
                <div>
                  <span>市场证据</span>
                  <strong>{marketMonitorStatus === 'available' ? '已接入' : '未命中'}</strong>
                </div>
                <div>
                  <span>关联榜单</span>
                  <strong>{marketMonitorTab || '-'}</strong>
                </div>
                <div>
                  <span>市场提示</span>
                  <strong>{marketRiskFlags.length > 0 ? `${marketRiskFlags.length} 条风险` : '无直接风险'}</strong>
                </div>
              </div>
              {marketFacts.length > 0 || marketRiskFlags.length > 0 ? (
                <div className="compact-news-list">
                  {[...marketFacts, ...marketRiskFlags].map((item) => (
                    <div key={item.key} className="news-stock-row">
                      <strong>{item.label}</strong>
                      {'severity' in item && item.severity ? <span className="status-chip warning">{item.severity}</span> : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">该股未出现在涨停、炸板、跌停或竞价监控名单；当前页不再跳转市场监控。</p>
              )}
            </article>

            <article className="workspace-band" role="region" aria-label="Strategy Signal">
              <div className="section-heading">
                <h2>策略信号</h2>
                <span className="muted">{profile.signals.length} signals</span>
              </div>
              {profile.signals.map((signal) => (
                <div key={`${signal.watchlist_id}-${signal.asset_id}-${signal.primary_signal}`} className="signal-card">
                  <div>
                    <strong>{signal.primary_signal}</strong>
                    <span>Priority {signal.priority}</span>
                  </div>
                  <p>{formatReason(signal.reason_json)}</p>
                  <div className="tag-stack">
                    {signal.signal_tags.map((tag) => (
                      <span key={tag} className="status-chip neutral">
                        {tag}
                      </span>
                    ))}
                    {signal.risk_tags.map((tag) => (
                      <span key={tag} className="risk-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {profile.signals.length === 0 ? <p className="muted">No active watchlist signal.</p> : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Research Coverage">
              <div className="section-heading">
                <h2>研报覆盖</h2>
                {isResearchReportsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              {researchReportsError ? <p className="error-text">{researchReportsError}</p> : null}
              {visibleResearchReports ? (
                <section className="stock-summary-strip" aria-label="Stock research report summary">
                  <div>
                    <span>Coverage</span>
                    <strong>90d reports {visibleResearchReports.summary.report_count_90d}</strong>
                  </div>
                  <div>
                    <span>30d Reports</span>
                    <strong>{visibleResearchReports.summary.report_count_30d}</strong>
                  </div>
                  <div>
                    <span>Brokers</span>
                    <strong>{visibleResearchReports.summary.broker_coverage_count_90d} brokers</strong>
                  </div>
                  <div>
                    <span>Latest Rating</span>
                    <strong>{formatValue(visibleResearchReports.summary.latest_rating)}</strong>
                  </div>
                  <div>
                    <span>Target Price</span>
                    <strong>{formatValue(visibleResearchReports.summary.latest_target_price)}</strong>
                  </div>
                </section>
              ) : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Related News">
              <div className="section-heading">
                <h2>相关新闻</h2>
                {isVisibleNewsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              {visibleAssetNews ? (
                <div className="metric-grid compact">
                  <span>
                    <span>1d News</span>
                    <strong>{visibleAssetNews.summary.news_count_1d}</strong>
                  </span>
                  <span>
                    <span>7d News</span>
                    <strong>{visibleAssetNews.summary.news_count_7d}</strong>
                  </span>
                  <span>
                    <span>Sources</span>
                    <strong>{visibleAssetNews.summary.source_count ?? 0}</strong>
                  </span>
                </div>
              ) : null}
              {visibleNewsError ? <p className="error-text">{visibleNewsError}</p> : null}
              {visibleAssetNews?.warnings?.length ? <p className="muted">{visibleAssetNews.warnings.join(' | ')}</p> : null}
              <div className="compact-news-list">
                {(visibleAssetNews?.items ?? []).map((item) => (
                  <a key={item.news_id} className="evidence-link-row" href={item.url} target="_blank" rel="noreferrer">
                    <strong>{item.title}</strong>
                    <span>{item.published_at.slice(0, 10)}</span>
                  </a>
                ))}
              </div>
              {!isVisibleNewsLoading && !visibleNewsError && (visibleAssetNews?.items.length ?? 0) === 0 ? (
                <p className="muted">No related news found.</p>
              ) : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Research Reports">
              <div className="section-heading">
                <h2>研报列表</h2>
                {isResearchReportsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              <div className="compact-news-list">
                {(visibleResearchReports?.items ?? []).map((report) =>
                  report.source_url ? (
                    <a
                      key={report.event_key}
                      className="evidence-link-row"
                      href={report.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <strong>{report.report_title}</strong>
                      <span>
                        {formatValue(report.broker)} / {formatValue(report.publish_date ?? report.report_date)}
                      </span>
                    </a>
                  ) : (
                    <div key={report.event_key} className="evidence-link-row">
                      <strong>{report.report_title}</strong>
                      <span>
                        {formatValue(report.broker)} / {formatValue(report.publish_date ?? report.report_date)}
                      </span>
                    </div>
                  )
                )}
              </div>
              {!isResearchReportsLoading && !researchReportsError && (visibleResearchReports?.items.length ?? 0) === 0 ? (
                <p className="muted">No research reports found.</p>
              ) : null}
            </article>

              </section>

              <details className="workspace-band stock-secondary-details" role="group" aria-label="二级信息">
                <summary>二级信息</summary>
                <section className="stock-evidence-grid stock-secondary-grid">
            <article className="workspace-band" role="region" aria-label="Factor / Score Breakdown">
              <div className="section-heading">
                <h2>因子/评分明细</h2>
                <span className="muted">{SCORE_VERSION}</span>
              </div>
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Factor</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {factorRows.map((row) => (
                    <tr key={`${row.group}-${row.name}`}>
                      <td>{row.group}</td>
                      <td>{row.name}</td>
                      <td>{formatValue(row.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {factorRows.length === 0 ? <p className="muted">No factor values available.</p> : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Review / Outcomes">
              <div className="section-heading">
                <h2>历史决策/结果</h2>
                <span className="muted">
                  {profile.decisions.length} decisions / {profile.outcomes.length} outcomes
                </span>
              </div>
              {profile.decisions.map((decision) => (
                <div key={decision.event_id} className="evidence-row">
                  <div>
                    <strong>{decision.decision_label}</strong>
                    <span>{decision.review_date}</span>
                  </div>
                  <p>{decision.notes || decision.follow_up_note}</p>
                  <span>{decision.evidence_path}</span>
                </div>
              ))}
              {profile.outcomes.map((outcome) => (
                <div key={outcome.outcome_event_id} className="evidence-row">
                  <div>
                    <strong>{outcome.outcome_status}</strong>
                    <span>{outcome.review_date}</span>
                  </div>
                  <p>
                    {outcome.decision_label} / {outcome.available_future_bars} future bars
                  </p>
                  <span>{outcome.outcome_artifact_path}</span>
                </div>
              ))}
              {profile.decisions.length === 0 && profile.outcomes.length === 0 ? (
                <p className="muted">No review decisions or outcomes recorded.</p>
              ) : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Evidence Timeline">
              <div className="section-heading">
                <h2>证据时间线</h2>
                <span className="muted">Current loaded evidence</span>
              </div>
              <div className="report-list compact stock-timeline">
                <div className="evidence-row stock-timeline-row">
                  <div>
                    <strong>Price coverage</strong>
                    <span>{profile.coverage?.bars?.end ?? endDate}</span>
                  </div>
                  <p>{profile.bars.length} loaded bars</p>
                </div>
                {profile.decisions.map((decision) => (
                  <div key={`timeline-${decision.event_id}`} className="evidence-row stock-timeline-row">
                    <div>
                      <strong>Review decision</strong>
                      <span>{decision.review_date}</span>
                    </div>
                    <p>{decision.decision_label}</p>
                  </div>
                ))}
                {profile.outcomes.map((outcome) => (
                  <div key={`timeline-${outcome.outcome_event_id}`} className="evidence-row stock-timeline-row">
                    <div>
                      <strong>Decision outcome</strong>
                      <span>{outcome.review_date}</span>
                    </div>
                    <p>{outcome.outcome_status}</p>
                    <span>{outcome.outcome_artifact_path}</span>
                  </div>
                ))}
                {(visibleAssetNews?.items ?? []).map((item) => (
                  <div key={`timeline-${item.news_id}`} className="evidence-row stock-timeline-row">
                    <div>
                      <strong>News item</strong>
                      <span>{item.published_at.slice(0, 10)}</span>
                    </div>
                    <p>News: {item.title}</p>
                  </div>
                ))}
                {(visibleResearchReports?.items ?? []).map((report) => (
                  <div key={`timeline-${report.event_key}`} className="evidence-row stock-timeline-row">
                    <div>
                      <strong>Research report</strong>
                      <span>{formatValue(report.publish_date ?? report.report_date)}</span>
                    </div>
                    <p>Research: {report.report_title}</p>
                  </div>
                ))}
                {(visibleAssetNews?.items.length ?? 0) === 0 ? (
                  <div className="evidence-row stock-timeline-row">
                    <div>
                      <strong>Latest news</strong>
                      <span>{latestNewsDate}</span>
                    </div>
                    <p>No loaded related news</p>
                  </div>
                ) : null}
                {(visibleResearchReports?.items.length ?? 0) === 0 ? (
                  <div className="evidence-row stock-timeline-row">
                    <div>
                      <strong>Latest research</strong>
                      <span>{latestReportDate}</span>
                    </div>
                    <p>No loaded research coverage</p>
                  </div>
                ) : null}
              </div>
            </article>

            <article className="workspace-band" role="region" aria-label="Search Matches">
              <div className="section-heading">
                <h2>搜索匹配</h2>
                {isSearchLoading ? <span className="muted">Searching...</span> : null}
              </div>
              {searchError ? <p className="error-text">{searchError}</p> : null}
              <div className="report-list compact">
                {assetMatches.map((match) => (
                  <button
                    key={match.asset_id}
                    className="list-row"
                    type="button"
                    onClick={() => setAssetId(match.asset_id)}
                  >
                    <span>{match.symbol}</span>
                    <strong>{match.name}</strong>
                    <span>{match.exchange}</span>
                  </button>
                ))}
              </div>
              {!isSearchLoading && assetMatches.length === 0 ? <p className="muted">No asset matches.</p> : null}
            </article>
                </section>
              </details>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
