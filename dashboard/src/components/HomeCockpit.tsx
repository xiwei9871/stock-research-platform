import { useEffect, useState } from 'react';
import {
  createResearchReviewAction,
  fetchBacktestStrategies,
  fetchMarketMonitorEod,
  fetchPlatformReadiness,
  fetchPlatformSummary,
  fetchPublicNews,
  fetchResearchCases,
  fetchResearchCaseDetail,
  fetchResearchEvidence,
  fetchResearchExternalDeliveryAttempts,
  fetchResearchExternalDeliveryPlan,
  fetchResearchPublicationPreview,
  fetchResearchPublicationSnapshots,
  fetchResearchPublishGate,
  fetchResearchQueueHealth,
  fetchStrategyScoreAudit
} from '../api/client';
import type {
  MarketMonitorPayload,
  PlatformReadiness,
  PlatformReadinessHealthGroup,
  PlatformReadinessHealthItem,
  PlatformSummary,
  PublicNewsItem,
  ResearchCase,
  ResearchCaseDetail,
  ResearchEvidenceArtifact,
  ResearchExternalDeliveryAttempt,
  ResearchExternalDeliveryPlan,
  ResearchPublicationPackage,
  ResearchPublicationSnapshotItem,
  ResearchPublishGate,
  ResearchPublishGateCase,
  ResearchQueueGapCase,
  ResearchQueueHealth,
  ResearchReviewActionType,
  StrategyScoreAuditSummary,
  StrategyCatalogItem
} from '../api/types';
import { resolvePlatformDisplayDate } from '../utils/platformDisplayDate';

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
  onOpenStrategy?: (strategyId: string) => void;
};

const ACTIVE_STRATEGY_IDS = ['lhb_shortline', 'mid_trend', 'tech_bottleneck'];
const STRATEGY_LABELS: Record<string, string> = {
  lhb_shortline: 'LHB Shortline Combo',
  mid_trend: 'Mid Trend Combo',
  tech_bottleneck: 'Tech Bottleneck Combo'
};

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '-';
}

function formatPercent(
  value: number | null | undefined,
  options: { signed?: boolean; fractionDigits?: number } = {}
) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  const prefix = options.signed && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(options.fractionDigits ?? 1)}%`;
}

function formatOneDecimal(value: number | null | undefined) {
  return typeof value === 'number' && !Number.isNaN(value) ? value.toFixed(1) : '-';
}

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' && !Number.isNaN(value) ? `${value.toFixed(1)} 分` : '-';
}

function formatBeijingMinute(value: string | null | undefined) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(date);
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day} ${byType.hour}:${byType.minute}`;
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

function dashboardAvailabilityLabel(readiness: PlatformReadiness | null) {
  if (!readiness?.policy) return '-';
  return readiness.policy.ready_for_dashboard ? '可查看' : '不可查看';
}

function publicationStatusLabel(readiness: PlatformReadiness | null) {
  if (!readiness?.policy) return '-';
  return readiness.policy.ready_for_publication ? '可发布' : '不可发布';
}

function policyStatusClass(isReady: boolean | null | undefined) {
  if (isReady === true) return 'ready';
  if (isReady === false) return 'blocked';
  return 'partial';
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

function strategyScoreAuditStatusLabel(audit: StrategyScoreAuditSummary | null, error: string | null) {
  if (error) return '不可用';
  if (!audit) return '-';
  if (audit.overall_status === 'ok') return '正常';
  if (audit.overall_status === 'warning') return '需关注';
  if (audit.overall_status === 'missing') return '待补齐';
  return audit.overall_status;
}

function strategyScoreAuditStatusClass(audit: StrategyScoreAuditSummary | null, error: string | null) {
  if (error) return 'blocked';
  if (!audit) return 'partial';
  if (audit.overall_status === 'ok') return 'ready';
  if (audit.overall_status === 'warning') return 'partial';
  if (audit.overall_status === 'missing') return 'blocked';
  return 'partial';
}

function strategyScoreAuditSummaryText(audit: StrategyScoreAuditSummary | null, error: string | null) {
  if (error) return '加载失败';
  if (!audit) return '读取中';
  if (audit.overall_status === 'missing') return '暂无审计产物';
  return `${audit.anomaly_row_count} 条异常`;
}

function strategyScoreAuditAnomalyLabel(anomalyType: string) {
  const labels: Record<string, string> = {
    mapped_score_without_raw_score: '映射分存在但原始分缺失',
    missing_candidate_source: '候选来源缺失',
    missing_raw_candidate_score: '原始候选分缺失',
    published_score_mismatch: '发布分与规则映射不一致',
    published_display_score_mismatch: '发布分与展示分不一致',
    stale_source: '来源数据过期'
  };
  return labels[anomalyType] ?? anomalyType;
}

function isKnownLhbMappingObservation(audit: StrategyScoreAuditSummary | null) {
  if (!audit || audit.overall_status !== 'warning') return false;
  const anomalyTypes = Object.keys(audit.anomaly_counts_by_type ?? {});
  if (anomalyTypes.length !== 1 || anomalyTypes[0] !== 'mapped_score_without_raw_score') return false;
  return (audit.strategies ?? []).every((strategy) =>
    strategy.strategy_id === 'lhb_shortline' ? strategy.anomaly_count > 0 : strategy.anomaly_count === 0
  );
}

function auditAffectedStrategies(audit: StrategyScoreAuditSummary | null) {
  return (audit?.strategies ?? []).filter((strategy) => strategy.anomaly_count > 0);
}

function auditSampleRows(audit: StrategyScoreAuditSummary | null) {
  return (audit?.sample_rows ?? []).slice(0, 5);
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function strategyEvidenceMetrics(strategy: StrategyCatalogItem) {
  const evidence = strategy.latest_evidence || '';
  const navMatch = evidence.match(/净值(?:约)?\s*([0-9]+(?:\.[0-9]+)?)/);
  const drawdownMatch = evidence.match(/(?:最大)?回撤(?:约)?\s*(-?[0-9]+(?:\.[0-9]+)?)%/);
  const nav = navMatch ? Number(navMatch[1]) : null;
  const contractStatus = strategy.latest_metrics?.contract_status ?? 'contract_mismatch';
  const contractReady = contractStatus === 'success';
  const totalReturnPct = contractReady
    ? strategy.latest_metrics?.total_return_pct ??
      (typeof nav === 'number' && !Number.isNaN(nav) ? (nav - 1) * 100 : null)
    : null;
  const maxDrawdownPct = contractReady
    ? strategy.latest_metrics?.max_drawdown_pct ?? (drawdownMatch ? Number(drawdownMatch[1]) : null)
    : null;
  let status = 'Evidence';
  if (strategy.latest_metrics?.signal_status === 'strategy_failed' || !contractReady) {
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
    latestDayReturnPct: contractReady ? strategy.latest_metrics?.latest_day_return_pct ?? null : null,
    latestPeriodReturnPct: contractReady
      ? strategy.latest_metrics?.latest_period_return_pct ?? strategy.latest_metrics?.latest_day_return_pct ?? null
      : null,
    latestPeriodLabel: strategy.latest_metrics?.latest_period_label ?? '最近交易日',
    latestDayDrawdownPct: contractReady ? strategy.latest_metrics?.latest_day_drawdown_pct ?? null : null,
    asOfDate: strategy.latest_metrics?.as_of_date ?? null,
    signalStatus: strategy.latest_metrics?.signal_status ?? 'no_position_rows',
    signalCount: strategy.latest_metrics?.signal_count ?? null,
    strategyVersion: strategy.latest_metrics?.strategy_version ?? null,
    contractId: strategy.latest_metrics?.contract_id ?? null,
    publishId: strategy.latest_metrics?.publish_id ?? null,
    artifactVersion: strategy.latest_metrics?.artifact_version ?? null,
    contractStatus,
    isLhbPolicy:
      contractReady &&
      strategy.strategy_id === 'lhb_shortline' &&
      strategy.latest_metrics?.publication_policy?.selection_policy ===
        'phase18c_top5_then_eligibility_no_refill',
    status,
    evidence
  };
}

function strategyVersionLabel(version: string | null) {
  if (version === 'lhb_v1_stable_safe_top5') return 'LHB V1 Stable Safe Top5';
  if (version === 'lhb_v1_safe_top5') return 'LHB V1 Safe Top5';
  return version;
}

function publicationHealth(status: string | null | undefined) {
  if (status === 'success') return { label: '数据正常', detail: '策略数据已完成更新' };
  if (!status) return { label: '数据更新中', detail: '等待最新策略数据' };
  return { label: '数据异常', detail: '最新策略数据暂不可用，请稍后复查' };
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
  if (metrics.contractStatus !== 'success') return '正式合同不匹配';
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

function blockedPublicationCount(readiness: PlatformReadiness | null) {
  const policy = readiness?.policy;
  if (!policy || policy.ready_for_publication) return 0;
  return Math.max(1, (policy.blocking_reasons ?? []).length);
}

function researchQueueBadgeLabel(
  loading: boolean,
  hasError: boolean,
  openCaseCount: number,
  evidenceGapCount: number,
  publicationBlockCount: number,
  evidenceCount: number
) {
  if (loading) return '加载中';
  if (hasError) return '不可用';
  if (openCaseCount === 0 && evidenceGapCount === 0 && publicationBlockCount === 0) return '无待处理';
  if (evidenceGapCount > 0 || publicationBlockCount > 0) return '需处理';
  return `${formatCount(evidenceCount)} evidence`;
}

function hasEvidenceGap(item: ResearchCase) {
  const status = (item.evidence_status || '').toLowerCase();
  return (
    item.evidence_count <= 0 ||
    item.missing_evidence_count > 0 ||
    item.partial_evidence_count > 0 ||
    (status !== '' && status !== 'complete')
  );
}

function gapReasonLabel(reason: string) {
  const labels: Record<string, string> = {
    no_evidence: '无 evidence',
    missing_evidence: '缺少 evidence',
    partial_evidence: '部分 evidence',
    incomplete_evidence_status: 'evidence 未完成',
    unknown_gap: '缺口原因待确认'
  };
  return labels[reason] ?? reason;
}

function gapReasonText(item: ResearchQueueGapCase) {
  const reasons = item.gap_reasons ?? [];
  if (!reasons.length) return item.gap_summary || '缺口原因待确认';
  return reasons.map(gapReasonLabel).join(' / ');
}

function reviewStatusLabel(status: string | null | undefined) {
  const labels: Record<string, string> = {
    pending: '待处理',
    reviewed: '已审阅',
    request_more_evidence: '需要补充证据',
    deferred: '暂缓处理'
  };
  return labels[String(status || 'pending')] ?? String(status || 'pending');
}

function reviewActionLabel(actionType: string | null | undefined) {
  const labels: Record<string, string> = {
    acknowledge_gap: '已知晓缺口',
    request_more_evidence: '需要补充证据',
    mark_reviewed: '标记已审阅',
    defer: '暂缓处理'
  };
  return labels[String(actionType || '')] ?? String(actionType || '-');
}

function publishGateStatusText(status: string | undefined) {
  if (status === 'research_ready') return '研究审阅已通过，可记录内部快照；外部发送未接入';
  if (status === 'empty') return '无研究队列，无法执行研究发布检查';
  if (status === 'failed') return '研究发布检查失败';
  if (status === 'entrypoint_missing') return '外部发送入口未接入';
  return '研究发布检查未通过';
}

function publishGateCaseReasonText(item: ResearchPublishGateCase) {
  const reasons = item.gap_reasons ?? [];
  if (!reasons.length) return item.gap_summary || '-';
  return reasons.map(gapReasonLabel).join(' / ');
}

function researchPublicationBlockCount(gate: ResearchPublishGate | null, readiness: PlatformReadiness | null) {
  if (!gate) return blockedPublicationCount(readiness);
  if (gate.status === 'empty' || gate.status === 'research_ready' || gate.research_ready_for_publication) return 0;
  const blockerCount = gate.blockers.reduce((total, blocker) => total + (blocker.count || 0), 0);
  const summaryBlockCount =
    gate.summary.pending_gap_count + gate.summary.request_more_evidence_count + gate.summary.error_count;
  return Math.max(blockerCount, summaryBlockCount, gate.top_blocked_cases.length, 1);
}

function researchQueueActionText(
  openCaseCount: number,
  evidenceGapCount: number,
  publicationBlockCount: number,
  hasError: boolean
) {
  if (hasError) return '展开查看接口错误，先不要据此判断今日无事项。';
  if (evidenceGapCount > 0 && publicationBlockCount > 0) return '先处理证据缺口，再处理发布保护。';
  if (evidenceGapCount > 0) return '先补齐或审阅证据缺口。';
  if (publicationBlockCount > 0) return '先处理平台发布保护。';
  if (openCaseCount > 0) return '有研究案例待审阅，可展开查看。';
  return '无需日常处理。';
}

function researchQueueSnapshotText(
  loading: boolean,
  hasError: boolean,
  openCaseCount: number,
  evidenceGapCount: number,
  publicationBlockCount: number
) {
  if (loading) return '研究队列加载中，正在检查今日案例和发布状态。';
  if (hasError) return '研究队列暂不可用。';
  if (openCaseCount === 0 && evidenceGapCount === 0 && publicationBlockCount === 0) return '今日暂无待处理研究事项。';
  return `今日有 ${formatCount(openCaseCount)} 个待审案例，${formatCount(evidenceGapCount)} 个证据缺口，${formatCount(
    publicationBlockCount
  )} 个发布阻塞。`;
}

function metadataText(metadata: Record<string, unknown>) {
  const entries = Object.entries(metadata ?? {}).filter(([, value]) => value !== undefined && value !== null && value !== '');
  if (!entries.length) return '';
  return entries
    .map(([key, value]) => `${key}=${Array.isArray(value) ? value.join(',') : String(value)}`)
    .join(' · ');
}

export function HomeCockpit({ onNavigate, onOpenStrategy }: HomeCockpitProps) {
  const [summary, setSummary] = useState<PlatformSummary | null>(null);
  const [strategies, setStrategies] = useState<StrategyCatalogItem[]>([]);
  const [marketMonitor, setMarketMonitor] = useState<MarketMonitorPayload | null>(null);
  const [marketMonitorLoading, setMarketMonitorLoading] = useState(true);
  const [newsItems, setNewsItems] = useState<PublicNewsItem[]>([]);
  const [readiness, setReadiness] = useState<PlatformReadiness | null>(null);
  const [readinessResolved, setReadinessResolved] = useState(false);
  const [readinessSucceeded, setReadinessSucceeded] = useState(false);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [scoreAudit, setScoreAudit] = useState<StrategyScoreAuditSummary | null>(null);
  const [scoreAuditError, setScoreAuditError] = useState<string | null>(null);
  const [researchCases, setResearchCases] = useState<ResearchCase[]>([]);
  const [researchEvidence, setResearchEvidence] = useState<ResearchEvidenceArtifact[]>([]);
  const [researchQueueHealth, setResearchQueueHealth] = useState<ResearchQueueHealth | null>(null);
  const [researchPublishGate, setResearchPublishGate] = useState<ResearchPublishGate | null>(null);
  const [researchPublicationPreview, setResearchPublicationPreview] = useState<ResearchPublicationPackage | null>(null);
  const [researchPublicationSnapshots, setResearchPublicationSnapshots] = useState<ResearchPublicationSnapshotItem[]>([]);
  const [researchExternalDeliveryPlan, setResearchExternalDeliveryPlan] = useState<ResearchExternalDeliveryPlan | null>(null);
  const [researchExternalDeliveryAttempts, setResearchExternalDeliveryAttempts] = useState<ResearchExternalDeliveryAttempt[]>([]);
  const [researchExternalDeliveryPlanLoading, setResearchExternalDeliveryPlanLoading] = useState(false);
  const [researchExternalDeliveryPlanError, setResearchExternalDeliveryPlanError] = useState<string | null>(null);
  const [researchPublicationPreviewLoading, setResearchPublicationPreviewLoading] = useState(false);
  const [researchPublicationPreviewError, setResearchPublicationPreviewError] = useState<string | null>(null);
  const [researchQueueLoading, setResearchQueueLoading] = useState(false);
  const [researchQueueError, setResearchQueueError] = useState<string | null>(null);
  const [healthCheckExpanded, setHealthCheckExpanded] = useState(false);
  const [researchQueueExpanded, setResearchQueueExpanded] = useState(false);
  const [selectedResearchCaseId, setSelectedResearchCaseId] = useState<string | null>(null);
  const [researchCaseDetail, setResearchCaseDetail] = useState<ResearchCaseDetail | null>(null);
  const [researchCaseDetailLoading, setResearchCaseDetailLoading] = useState(false);
  const [researchCaseDetailError, setResearchCaseDetailError] = useState<string | null>(null);
  const [reviewActionComment, setReviewActionComment] = useState('');
  const [reviewActionSubmitting, setReviewActionSubmitting] = useState<ResearchReviewActionType | null>(null);
  const [reviewActionError, setReviewActionError] = useState<string | null>(null);
  const [widgetWarnings, setWidgetWarnings] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const visibleStrategies = activeStrategies(strategies);
  const baseDataHealth = healthGroup(readiness, 'base_data');
  const strategyHealth = healthGroup(readiness, 'strategy_execution');
  const reviewHealth = healthGroup(readiness, 'review_chain');
  const contentHealth = healthGroup(readiness, 'content_chain');
  const healthGroups = readiness?.health_groups ?? [];
  const policy = readiness?.policy;
  const showPublicationGuard =
    Boolean(policy) &&
    (!policy?.ready_for_publication || (policy?.blocking_reasons ?? []).length > 0 || (policy?.warnings ?? []).length > 0);
  const displayTradeDate =
    readinessResolved && readinessSucceeded
      ? resolvePlatformDisplayDate(readiness, {
          allowLegacyFallback: true,
          legacyFallbackDates: [summary?.latest_market_date]
        }) || '-'
      : '-';
  const openResearchCaseCount = researchCases.filter((item) => item.status.toLowerCase() === 'open').length;
  const evidenceGapCount = researchCases.filter(hasEvidenceGap).length;
  const researchQueueSummary = researchQueueHealth?.summary;
  const displayedOpenResearchCaseCount = researchQueueSummary?.open_case_count ?? openResearchCaseCount;
  const displayedEvidenceGapCount = researchQueueSummary?.evidence_gap_count ?? evidenceGapCount;
  const displayedPublicationBlockCount = researchPublicationBlockCount(researchPublishGate, readiness);
  const researchQueueHasError = Boolean(researchQueueError);
  const researchQueueSnapshot = researchQueueSnapshotText(
    researchQueueLoading,
    researchQueueHasError,
    displayedOpenResearchCaseCount,
    displayedEvidenceGapCount,
    displayedPublicationBlockCount
  );
  const researchQueueAction = researchQueueActionText(
    displayedOpenResearchCaseCount,
    displayedEvidenceGapCount,
    displayedPublicationBlockCount,
    researchQueueHasError
  );
  const researchQueueRefreshText = researchQueueHealth?.last_refresh?.finished_at
    ? `最近刷新 ${formatBeijingMinute(researchQueueHealth.last_refresh.finished_at)}`
    : '';
  const topResearchCases = researchCases.slice(0, 5);
  const topGapCases = researchQueueHealth?.status === 'partial' ? (researchQueueHealth.top_gap_cases ?? []).slice(0, 5) : [];
  const latestPublicationSnapshot = researchPublicationSnapshots[0] ?? null;
  const latestExternalDeliveryAttempt = researchExternalDeliveryAttempts[0] ?? null;

  useEffect(() => {
    let ignore = false;
    setIsLoading(true);
    setError(null);
    setWidgetWarnings([]);
    setMarketMonitor(null);
    setMarketMonitorLoading(true);
    setReadiness(null);
    setReadinessResolved(false);
    setReadinessSucceeded(false);
    setReadinessError(null);
    setScoreAudit(null);
    setScoreAuditError(null);

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
          setReadinessResolved(true);
          setReadinessSucceeded(true);
          setReadinessError(null);
        }
      },
      (err: unknown) => {
        if (!ignore) {
          setReadiness(null);
          setReadinessResolved(true);
          setReadinessSucceeded(false);
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
      setScoreAuditError(null);
      return;
    }

    let ignore = false;
    void fetchStrategyScoreAudit(displayTradeDate).then(
      (payload) => {
        if (!ignore) {
          setScoreAudit(payload);
          setScoreAuditError(null);
        }
      },
      (err: unknown) => {
        if (!ignore) {
          setScoreAudit(null);
          setScoreAuditError(errorMessage(err));
        }
      }
    );

    return () => {
      ignore = true;
    };
  }, [displayTradeDate]);

  useEffect(() => {
    if (!displayTradeDate || displayTradeDate === '-') {
      setResearchCases([]);
      setResearchEvidence([]);
      setResearchQueueHealth(null);
      setResearchPublishGate(null);
      setResearchPublicationPreview(null);
      setResearchPublicationSnapshots([]);
      setResearchExternalDeliveryPlan(null);
      setResearchExternalDeliveryAttempts([]);
      setResearchExternalDeliveryPlanLoading(false);
      setResearchExternalDeliveryPlanError(null);
      setResearchPublicationPreviewLoading(false);
      setResearchPublicationPreviewError(null);
      setResearchQueueLoading(false);
      setResearchQueueError(null);
      setSelectedResearchCaseId(null);
      setResearchCaseDetail(null);
      setResearchCaseDetailError(null);
      setReviewActionComment('');
      setReviewActionError(null);
      return;
    }

    let ignore = false;
    setResearchQueueLoading(true);
    setResearchQueueError(null);
    setResearchExternalDeliveryPlan(null);
    setResearchExternalDeliveryAttempts([]);
    setResearchExternalDeliveryPlanLoading(false);
    setResearchExternalDeliveryPlanError(null);
    void Promise.all([
      fetchResearchCases({ tradeDate: displayTradeDate, status: 'open', limit: 100 }),
      fetchResearchEvidence({ limit: 100 }),
      fetchResearchQueueHealth({ tradeDate: displayTradeDate }),
      fetchResearchPublishGate({ tradeDate: displayTradeDate }),
      fetchResearchPublicationSnapshots({ tradeDate: displayTradeDate, limit: 5 })
    ]).then(
      ([casesPayload, evidencePayload, healthPayload, publishGatePayload, snapshotsPayload]) => {
        if (!ignore) {
          setResearchCases(casesPayload.items);
          setResearchEvidence(evidencePayload.items);
          setResearchQueueHealth(healthPayload);
          setResearchPublishGate(publishGatePayload);
          setResearchPublicationSnapshots(snapshotsPayload.items);
          const latestSnapshot = snapshotsPayload.items[0] ?? null;
          if (latestSnapshot) {
            setResearchExternalDeliveryPlanLoading(true);
            void Promise.all([
              fetchResearchExternalDeliveryPlan({
                publicationSnapshotId: latestSnapshot.publication_snapshot_id,
                channel: 'feishu_preview'
              }),
              fetchResearchExternalDeliveryAttempts({
                publicationSnapshotId: latestSnapshot.publication_snapshot_id,
                limit: 5
              })
            ]).then(
              ([planPayload, attemptsPayload]) => {
                if (!ignore) {
                  setResearchExternalDeliveryPlan(planPayload);
                  setResearchExternalDeliveryAttempts(attemptsPayload.items);
                  setResearchExternalDeliveryPlanLoading(false);
                  setResearchExternalDeliveryPlanError(null);
                }
              },
              (err: unknown) => {
                if (!ignore) {
                  setResearchExternalDeliveryPlan(null);
                  setResearchExternalDeliveryAttempts([]);
                  setResearchExternalDeliveryPlanLoading(false);
                  setResearchExternalDeliveryPlanError(`外部发送预案不可用：${errorMessage(err)}`);
                }
              }
            );
          }
          setResearchPublicationPreview(null);
          setResearchPublicationPreviewError(null);
          setSelectedResearchCaseId((current) =>
            current && casesPayload.items.some((item) => item.case_id === current) ? current : null
          );
          setResearchQueueLoading(false);
          setResearchQueueError(null);
        }
      },
      (err: unknown) => {
        if (!ignore) {
          setResearchCases([]);
          setResearchEvidence([]);
          setResearchQueueHealth(null);
          setResearchPublishGate(null);
          setResearchPublicationPreview(null);
          setResearchPublicationSnapshots([]);
          setResearchExternalDeliveryPlan(null);
          setResearchExternalDeliveryAttempts([]);
          setResearchExternalDeliveryPlanLoading(false);
          setResearchExternalDeliveryPlanError(null);
          setResearchPublicationPreviewLoading(false);
          setResearchPublicationPreviewError(null);
          setSelectedResearchCaseId(null);
          setResearchCaseDetail(null);
          setResearchQueueLoading(false);
          setResearchQueueError(`研究队列不可用：${errorMessage(err)}`);
        }
      }
    );

    return () => {
      ignore = true;
    };
  }, [displayTradeDate]);

  const loadResearchPublicationPreview = () => {
    if (!displayTradeDate || displayTradeDate === '-') return;
    setResearchPublicationPreviewLoading(true);
    setResearchPublicationPreviewError(null);
    void fetchResearchPublicationPreview({ tradeDate: displayTradeDate }).then(
      (payload) => {
        setResearchPublicationPreview(payload);
        setResearchPublicationPreviewLoading(false);
        setResearchPublicationPreviewError(null);
      },
      (err: unknown) => {
        setResearchPublicationPreview(null);
        setResearchPublicationPreviewLoading(false);
        setResearchPublicationPreviewError(`发布预览不可用：${errorMessage(err)}`);
      }
    );
  };

  const openResearchCaseDetail = (caseId: string) => {
    setSelectedResearchCaseId(caseId);
    setResearchCaseDetail(null);
    setResearchCaseDetailLoading(true);
    setResearchCaseDetailError(null);
    setReviewActionError(null);
    void fetchResearchCaseDetail(caseId).then(
      (payload) => {
        setResearchCaseDetail(payload);
        setResearchCaseDetailLoading(false);
        setResearchCaseDetailError(null);
      },
      (err: unknown) => {
        setResearchCaseDetail(null);
        setResearchCaseDetailLoading(false);
        setResearchCaseDetailError(`研究案例详情不可用：${errorMessage(err)}`);
      }
    );
  };

  const refreshResearchQueueForReviewAction = (caseId: string) =>
    Promise.all([
      fetchResearchCaseDetail(caseId),
      fetchResearchCases({ tradeDate: displayTradeDate, status: 'open', limit: 100 }),
      fetchResearchEvidence({ limit: 100 }),
      fetchResearchQueueHealth({ tradeDate: displayTradeDate }),
      fetchResearchPublishGate({ tradeDate: displayTradeDate })
    ]).then(([detailPayload, casesPayload, evidencePayload, healthPayload, publishGatePayload]) => {
      setResearchCaseDetail(detailPayload);
      setResearchCases(casesPayload.items);
      setResearchEvidence(evidencePayload.items);
      setResearchQueueHealth(healthPayload);
      setResearchPublishGate(publishGatePayload);
    });

  const submitReviewAction = (actionType: ResearchReviewActionType) => {
    if (!researchCaseDetail || !displayTradeDate || displayTradeDate === '-') return;
    const currentCase = researchCaseDetail.case;
    setReviewActionSubmitting(actionType);
    setReviewActionError(null);
    void createResearchReviewAction({
      case_id: currentCase.case_id,
      trade_date: currentCase.trade_date || displayTradeDate,
      asset_id: currentCase.asset_id,
      action_type: actionType,
      gap_reasons: researchCaseDetail.gap_reasons ?? [],
      reviewer: 'operator',
      comment: reviewActionComment,
      source_context: {
        from: 'home_cockpit_gap_detail',
        case_source_type: currentCase.source_type,
        case_source_id: currentCase.source_id
      }
    }).then(
      () =>
        refreshResearchQueueForReviewAction(currentCase.case_id).then(() => {
          setReviewActionComment('');
          setReviewActionSubmitting(null);
          setReviewActionError(null);
        }),
      (err: unknown) => {
        setReviewActionSubmitting(null);
        setReviewActionError(`审阅动作写入失败：${errorMessage(err)}`);
      }
    );
  };

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
        <div>
          <span>看板状态</span>
          <strong className={`readiness-value ${policyStatusClass(policy?.ready_for_dashboard)}`}>
            {dashboardAvailabilityLabel(readiness)}
          </strong>
        </div>
        <div>
          <span>发布状态</span>
          <strong className={`readiness-value ${policyStatusClass(policy?.ready_for_publication)}`}>
            {publicationStatusLabel(readiness)}
          </strong>
        </div>
        <div className="status-strip-audit-cell">
          <span>策略打分审计</span>
          <strong className={`readiness-value ${strategyScoreAuditStatusClass(scoreAudit, scoreAuditError)}`}>
            {strategyScoreAuditStatusLabel(scoreAudit, scoreAuditError)}
          </strong>
          <small>{strategyScoreAuditSummaryText(scoreAudit, scoreAuditError)}</small>
        </div>
      </section>

      {showPublicationGuard ? (
        <section className="workspace-panel publication-guard-panel" aria-label="平台发布保护">
          <div className="section-heading">
            <h2>平台发布保护</h2>
            <span className={`status-chip ${policy?.ready_for_publication ? 'success' : 'warning'}`}>
              {publicationStatusLabel(readiness)}
            </span>
          </div>
          {(policy?.blocking_reasons ?? []).length > 0 ? (
            <div className="tag-stack">
              {(policy?.blocking_reasons ?? []).map((reason) => (
                <span className="status-chip warning" key={reason}>
                  {reason}
                </span>
              ))}
            </div>
          ) : null}
          {(policy?.warnings ?? []).length > 0 ? (
            <div className="tag-stack">
              {(policy?.warnings ?? []).map((warning) => (
                <span className="status-chip neutral" key={warning}>
                  {formatReadinessWarning(warning)}
                </span>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {scoreAudit?.overall_status === 'warning' ? (
        <section className="workspace-panel audit-action-panel" aria-label="策略打分审计处理建议">
          <div className="section-heading">
            <div>
              <h2>策略打分审计处理建议</h2>
              <p className="muted">
                {isKnownLhbMappingObservation(scoreAudit)
                  ? '当前异常集中在 LHB 的已知观察项，可继续使用系统，同时跟踪原始分审计链补齐。'
                  : '审计发现异常，请先确认影响范围，再决定是按已知观察项处理还是按系统问题排查。'}
              </p>
            </div>
            <span className={`status-chip ${isKnownLhbMappingObservation(scoreAudit) ? 'neutral' : 'warning'}`}>
              {isKnownLhbMappingObservation(scoreAudit) ? '已知观察项' : '需人工处理'}
            </span>
          </div>

          <div className="audit-action-grid">
            <div className="audit-action-card">
              <span>异常总数</span>
              <strong>{scoreAudit.anomaly_row_count} 条</strong>
            </div>
            {(auditAffectedStrategies(scoreAudit).length ? auditAffectedStrategies(scoreAudit) : scoreAudit.strategies).map((strategy) => (
              <div className="audit-action-card" key={strategy.strategy_id}>
                <span>{STRATEGY_LABELS[strategy.strategy_id] ?? strategy.strategy_id}</span>
                <strong>{strategy.anomaly_count} 条异常</strong>
              </div>
            ))}
          </div>

          <div className="tag-stack">
            {Object.entries(scoreAudit.anomaly_counts_by_type ?? {}).map(([anomalyType, count]) => (
              <span className="status-chip warning" key={anomalyType}>
                {`${strategyScoreAuditAnomalyLabel(anomalyType)} ${count} 条`}
              </span>
            ))}
          </div>

          {auditSampleRows(scoreAudit).length > 0 ? (
            <div className="audit-sample-list" aria-label="审计异常样本">
              {auditSampleRows(scoreAudit).map((row) => (
                <div className="audit-sample-row" key={`${row.strategy_id ?? ''}:${row.asset_id}`}>
                  <strong>{row.asset_id}</strong>
                  <span>{STRATEGY_LABELS[row.strategy_id ?? ''] ?? row.strategy_id ?? '未知策略'}</span>
                  <span>{(row.anomaly_flags ?? []).map((flag) => strategyScoreAuditAnomalyLabel(flag)).join(' / ') || '异常待确认'}</span>
                </div>
              ))}
            </div>
          ) : null}

          <div className="compact-toolbar">
            <button type="button" onClick={() => onNavigate('reviewQueue')}>
              查看复盘队列
            </button>
            <button type="button" onClick={() => onNavigate('strategyLab')}>
              打开策略实验室
            </button>
            <button type="button" onClick={() => onNavigate('generatedReports')}>
              查看生成报告
            </button>
          </div>
        </section>
      ) : null}

      <section className="workspace-panel collapsible-panel health-check-panel" aria-label="平台健康检查">
        <div className="collapsible-panel-heading">
          <div className="collapsible-panel-title">
            <h2>健康检查</h2>
            <p className="muted">
              基础数据 {readinessCount(baseDataHealth, 4)} · 策略执行 {readinessCount(strategyHealth, 3)} · 复盘链路{' '}
              {readinessCount(reviewHealth, 3)} · 内容链路 {readinessCount(contentHealth, 3)}
            </p>
          </div>
          <div className="section-heading-actions collapsible-panel-actions">
            <button
              type="button"
              aria-expanded={healthCheckExpanded}
              aria-controls="health-check-details"
              onClick={() => setHealthCheckExpanded((value) => !value)}
            >
              {healthCheckExpanded ? '收起' : '展开'}
            </button>
          </div>
        </div>
        {healthCheckExpanded ? (
          <div className="collapsible-panel-body health-check-grid" id="health-check-details">
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
        ) : null}
      </section>

      <section className="workspace-panel collapsible-panel research-workbench-panel" aria-label="今日研究队列">
        <div className="collapsible-panel-heading">
          <div className="collapsible-panel-title">
            <h2>今日研究队列</h2>
            <p className="muted">{displayTradeDate === '-' ? '等待平台日期' : `研究日期 ${displayTradeDate}`}</p>
            <p className="research-queue-snapshot">{researchQueueSnapshot}</p>
            <p className="research-queue-action">{researchQueueAction}</p>
            {researchQueueRefreshText ? <p className="muted">{researchQueueRefreshText}</p> : null}
          </div>
          <div className="section-heading-actions collapsible-panel-actions">
            <span className="status-chip neutral">
              {researchQueueBadgeLabel(
                researchQueueLoading,
                researchQueueHasError,
                displayedOpenResearchCaseCount,
                displayedEvidenceGapCount,
                displayedPublicationBlockCount,
                researchEvidence.length
              )}
            </span>
            <button
              type="button"
              aria-expanded={researchQueueExpanded}
              aria-controls="research-queue-details"
              onClick={() => setResearchQueueExpanded((value) => !value)}
            >
              {researchQueueExpanded ? '收起' : '展开'}
            </button>
          </div>
        </div>
        {researchQueueExpanded ? (
          <div className="collapsible-panel-body research-queue-details" id="research-queue-details">
            <div className="research-queue-summary">
              <div>
                <span>Open Cases</span>
                <strong>{researchQueueLoading ? '-' : formatCount(displayedOpenResearchCaseCount)}</strong>
              </div>
              <div>
                <span>Evidence Gaps</span>
                <strong>{researchQueueLoading ? '-' : formatCount(displayedEvidenceGapCount)}</strong>
              </div>
              <div>
                <span>Publication Blocks</span>
                <strong>{formatCount(displayedPublicationBlockCount)}</strong>
              </div>
            </div>
            {researchQueueHealth ? (
              <div className="research-queue-health" aria-label="Research queue health">
                <div>
                  <span>Queue Health</span>
                  <strong>{researchQueueHealth.status}</strong>
                </div>
                <div>
                  <span>Last Refresh</span>
                  <strong>{formatBeijingMinute(researchQueueHealth.last_refresh?.finished_at)}</strong>
                </div>
                <div>
                  <span>Cases</span>
                  <strong>{formatCount(researchQueueHealth.summary.case_count)}</strong>
                </div>
                <div>
                  <span>Claims</span>
                  <strong>{formatCount(researchQueueHealth.summary.claim_count)}</strong>
                </div>
                <div>
                  <span>Evidence</span>
                  <strong>{formatCount(researchQueueHealth.summary.evidence_artifact_count)}</strong>
                </div>
                <div>
                  <span>Links</span>
                  <strong>{formatCount(researchQueueHealth.summary.evidence_link_count)}</strong>
                </div>
                <div>
                  <span>Unmatched Digest</span>
                  <strong>{formatCount(researchQueueHealth.summary.unmatched_digest_count)}</strong>
                </div>
                <div>
                  <span>Review</span>
                  <strong>{researchQueueHealth.can_review ? '可审阅' : '不可审阅'}</strong>
                </div>
                  <div>
                    <span>Research Publish</span>
                    <strong>{researchQueueHealth.can_publish_research_queue ? '可发布' : '外部发送未接入'}</strong>
                  </div>
              </div>
            ) : null}
            {researchPublishGate ? (
              <div className="research-publish-gate" aria-label="研究发布检查">
                <div className="research-publish-gate-heading">
                  <div>
                    <strong>研究发布检查</strong>
                    <span>{publishGateStatusText(researchPublishGate.status)}</span>
                  </div>
                  <div className="research-publish-gate-actions">
                    <span className="status-chip neutral">{researchPublishGate.status}</span>
                    <button type="button" onClick={loadResearchPublicationPreview} disabled={researchPublicationPreviewLoading}>
                      {researchPublicationPreviewLoading ? '生成预览中' : '查看发布预览'}
                    </button>
                  </div>
                </div>
                <div className="research-publish-gate-summary">
                  <div>
                    <span>Research Publish Gate</span>
                    <strong>{researchPublishGate.status}</strong>
                  </div>
                  <div>
                    <span>Actual Publish</span>
                    <strong>外部发送入口未接入</strong>
                  </div>
                  <div>
                    <span>Internal Snapshot</span>
                    <strong>{researchPublishGate.internal_snapshot_enabled ? 'Gate 通过后可记录' : 'Gate 未通过，不能记录'}</strong>
                  </div>
                  <div>
                    <span>Pending Gaps</span>
                    <strong>{formatCount(researchPublishGate.summary.pending_gap_count)}</strong>
                  </div>
                  <div>
                    <span>Need Evidence</span>
                    <strong>{formatCount(researchPublishGate.summary.request_more_evidence_count)}</strong>
                  </div>
                </div>
                {researchPublishGate.blockers.length > 0 ? (
                  <div className="research-publish-blockers" aria-label="研究发布检查阻断原因">
                    {researchPublishGate.blockers.slice(0, 3).map((blocker) => (
                      <div className="research-publish-blocker" key={blocker.code}>
                        <strong>{blocker.code}</strong>
                        <span>{blocker.message}</span>
                        <small>{formatCount(blocker.count)}</small>
                      </div>
                    ))}
                  </div>
                ) : null}
                {researchPublishGate.top_blocked_cases.length > 0 ? (
                  <div className="research-gap-list" aria-label="研究发布检查阻断案例">
                    <div className="research-gap-heading">
                      <strong>Top Blocked Cases</strong>
                      <span>{formatCount(researchPublishGate.top_blocked_cases.length)}</span>
                    </div>
                    {researchPublishGate.top_blocked_cases.map((item) => (
                      <div className="research-case-row" key={`publish-gate:${item.case_id}`}>
                        <strong>{item.title || item.case_id}</strong>
                        <span>{item.asset_id || '-'}</span>
                        <span>{item.theme || '-'}</span>
                        <span>{reviewStatusLabel(item.review_status)}</span>
                        <span>{publishGateCaseReasonText(item)}</span>
                        <button type="button" onClick={() => openResearchCaseDetail(item.case_id)}>
                          审阅
                        </button>
                      </div>
                    ))}
                  </div>
                ) : null}
                {researchPublicationPreviewError ? <p className="error-text">{researchPublicationPreviewError}</p> : null}
                {researchPublicationPreview ? (
                  <div className="research-publication-preview" aria-label="发布预览">
                    <div className="research-publication-preview-heading">
                      <div>
                        <strong>发布预览</strong>
                        <span>预览，不是发布</span>
                      </div>
                      <span className="status-chip neutral">{`publishable=${
                        researchPublicationPreview.publishable ? 'true' : 'false'
                      }`}</span>
                    </div>
                    <div className="research-source-trace">
                      <span>Package</span>
                      <strong>{researchPublicationPreview.package_id}</strong>
                    </div>
                    <div className="research-publication-preview-summary">
                      <div>
                        <span>Gate</span>
                        <strong>{researchPublicationPreview.gate.status}</strong>
                      </div>
                      <div>
                        <span>Actual Publish</span>
                        <strong>外部发送入口未接入</strong>
                      </div>
                      <div>
                        <span>Internal Snapshot</span>
                        <strong>
                          {researchPublicationPreview.internal_snapshot_enabled ? 'Gate 通过后可记录' : 'Gate 未通过，不能记录'}
                        </strong>
                      </div>
                      <div>
                        <span>Cases</span>
                        <strong>{formatCount(researchPublicationPreview.summary.case_count)}</strong>
                      </div>
                      <div>
                        <span>Claims</span>
                        <strong>{formatCount(researchPublicationPreview.summary.claim_count)}</strong>
                      </div>
                      <div>
                        <span>Evidence</span>
                        <strong>{formatCount(researchPublicationPreview.summary.evidence_count)}</strong>
                      </div>
                      <div>
                        <span>Gaps</span>
                        <strong>{formatCount(researchPublicationPreview.summary.gap_count)}</strong>
                      </div>
                    </div>
                    {researchPublicationPreview.blockers.length > 0 ? (
                      <div className="research-publish-blockers" aria-label="发布预览阻断原因">
                        {researchPublicationPreview.blockers.slice(0, 3).map((blocker) => (
                          <div className="research-publish-blocker" key={`preview:${blocker.code}`}>
                            <strong>{blocker.code}</strong>
                            <span>{blocker.message}</span>
                            <small>{formatCount(blocker.count)}</small>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="research-publication-preview" aria-label="内部发布快照">
                  <div className="research-publication-preview-heading">
                    <div>
                      <strong>内部发布快照</strong>
                      <span>只代表内部 research queue snapshot，不代表外部已发送</span>
                    </div>
                    <span className="status-chip neutral">{`snapshot_count=${formatCount(researchPublicationSnapshots.length)}`}</span>
                  </div>
                  {latestPublicationSnapshot ? (
                    <>
                      <div className="research-source-trace">
                        <span>Latest Snapshot</span>
                        <strong>{latestPublicationSnapshot.publication_snapshot_id}</strong>
                      </div>
                      <div className="research-publication-preview-summary">
                        <div>
                          <span>Created</span>
                          <strong>{formatBeijingMinute(latestPublicationSnapshot.created_at)}</strong>
                        </div>
                        <div>
                          <span>Channel</span>
                          <strong>{latestPublicationSnapshot.channel}</strong>
                        </div>
                        <div>
                          <span>Gate</span>
                          <strong>{latestPublicationSnapshot.gate_status}</strong>
                        </div>
                        <div>
                          <span>Cases</span>
                          <strong>{formatCount(latestPublicationSnapshot.case_count)}</strong>
                        </div>
                        <div>
                          <span>Claims</span>
                          <strong>{formatCount(latestPublicationSnapshot.claim_count)}</strong>
                        </div>
                        <div>
                          <span>Evidence</span>
                          <strong>{formatCount(latestPublicationSnapshot.evidence_count)}</strong>
                        </div>
                        <div>
                          <span>Gaps</span>
                          <strong>{formatCount(latestPublicationSnapshot.gap_count)}</strong>
                        </div>
                        <div>
                          <span>External Delivery</span>
                          <strong>外部发送状态：未接入</strong>
                        </div>
                      </div>
                    </>
                  ) : (
                    <p className="muted">暂无内部发布快照</p>
                  )}
                </div>
                {latestPublicationSnapshot ? (
                  <div className="research-publication-preview" aria-label="外部发送预案">
                    <div className="research-publication-preview-heading">
                      <div>
                        <strong>外部发送预案</strong>
                        <span>外部发送预案，仅 dry-run</span>
                      </div>
                      <span className="status-chip neutral">真实外部发送尚未接入</span>
                    </div>
                    {researchExternalDeliveryPlanLoading ? <p className="muted">外部发送预案加载中...</p> : null}
                    {researchExternalDeliveryPlanError ? <p className="error-text">{researchExternalDeliveryPlanError}</p> : null}
                    {researchExternalDeliveryPlan ? (
                      <>
                        <div className="research-source-trace">
                          <span>Delivery Plan</span>
                          <strong>{researchExternalDeliveryPlan.delivery_plan_id}</strong>
                        </div>
                        <div className="research-publication-preview-summary">
                          <div>
                            <span>Channel Preview</span>
                            <strong>{researchExternalDeliveryPlan.channel}</strong>
                          </div>
                          <div>
                            <span>External Send</span>
                            <strong>{researchExternalDeliveryPlan.external_send_enabled ? 'enabled' : 'disabled'}</strong>
                          </div>
                          <div>
                            <span>Message Title</span>
                            <strong>{researchExternalDeliveryPlan.message.title || '-'}</strong>
                          </div>
                          <div>
                            <span>Sections</span>
                            <strong>{formatCount(researchExternalDeliveryPlan.message.sections.length)}</strong>
                          </div>
                        </div>
                        <p className="muted">{researchExternalDeliveryPlan.message.summary}</p>
                        <p className="muted">不会发送飞书/邮件；真实外部发送尚未接入。</p>
                        {researchExternalDeliveryPlan.warnings.length > 0 ? (
                          <div className="tag-stack" aria-label="外部发送预案警告">
                            {researchExternalDeliveryPlan.warnings.map((warning) => (
                              <span className="status-chip neutral" key={warning}>
                                {warning}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                ) : null}
                <div className="research-publication-preview" aria-label="发送尝试账本">
                  <div className="research-publication-preview-heading">
                    <div>
                      <strong>发送尝试账本</strong>
                      <span>只记录 dry-run 尝试，不代表外部发布完成</span>
                    </div>
                    <span className="status-chip neutral">{`attempt_count=${formatCount(researchExternalDeliveryAttempts.length)}`}</span>
                  </div>
                  {latestExternalDeliveryAttempt ? (
                    <>
                      <div className="research-source-trace">
                        <span>Latest Attempt</span>
                        <strong>{latestExternalDeliveryAttempt.delivery_attempt_id}</strong>
                      </div>
                      <div className="research-publication-preview-summary">
                        <div>
                          <span>Status</span>
                          <strong>{latestExternalDeliveryAttempt.status}</strong>
                        </div>
                        <div>
                          <span>Channel</span>
                          <strong>{latestExternalDeliveryAttempt.channel}</strong>
                        </div>
                        <div>
                          <span>Dry Run</span>
                          <strong>{latestExternalDeliveryAttempt.dry_run ? 'true' : 'false'}</strong>
                        </div>
                        <div>
                          <span>External Send</span>
                          <strong>{latestExternalDeliveryAttempt.external_send_enabled ? 'enabled' : 'disabled'}</strong>
                        </div>
                        <div>
                          <span>Created</span>
                          <strong>{formatBeijingMinute(latestExternalDeliveryAttempt.created_at)}</strong>
                        </div>
                        <div>
                          <span>Error</span>
                          <strong>{latestExternalDeliveryAttempt.error_code || latestExternalDeliveryAttempt.error_message || '-'}</strong>
                        </div>
                      </div>
                    </>
                  ) : (
                    <p className="muted">暂无外部发送尝试记录</p>
                  )}
                </div>
              </div>
            ) : null}
            {researchQueueError ? <p className="error-text">{researchQueueError}</p> : null}
            {researchQueueLoading ? <p className="muted">研究队列加载中...</p> : null}
            {!researchQueueLoading && !researchQueueError && topResearchCases.length === 0 ? (
              <p className="muted">今日暂无 open research case。</p>
            ) : null}
            {topResearchCases.length > 0 ? (
              <div className="research-case-list" aria-label="Top research cases">
                {topResearchCases.map((item) => (
                  <div className="research-case-row" key={item.case_id}>
                    <strong>{item.title || item.case_id}</strong>
                    <span>{item.asset_id || '-'}</span>
                    <span>{item.theme || '-'}</span>
                    <span>{item.status}</span>
                    <span>{`${item.evidence_count} evidence / ${item.claim_count} claims`}</span>
                    <button type="button" onClick={() => openResearchCaseDetail(item.case_id)}>
                      审阅
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
            {topGapCases.length > 0 ? (
              <div className="research-gap-list" aria-label="待处理证据缺口">
                <div className="research-gap-heading">
                  <strong>待处理证据缺口</strong>
                  <span>{`${formatCount(topGapCases.length)} / ${formatCount(displayedEvidenceGapCount)}`}</span>
                </div>
                {topGapCases.map((item) => (
                  <div className="research-case-row" key={`gap:${item.case_id}`}>
                    <strong>{item.title || item.case_id}</strong>
                    <span>{item.asset_id || '-'}</span>
                    <span>{item.theme || '-'}</span>
                    <span>{gapReasonText(item)}</span>
                    <span>{`${item.evidence_count} evidence / ${item.claim_count} claims`}</span>
                    <button type="button" onClick={() => openResearchCaseDetail(item.case_id)}>
                      审阅
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {selectedResearchCaseId && researchQueueExpanded ? (
          <div className="research-case-detail" role="region" aria-label="研究案例详情">
            {researchCaseDetailLoading ? <p className="muted">研究案例详情加载中...</p> : null}
            {researchCaseDetailError ? <p className="error-text">{researchCaseDetailError}</p> : null}
            {!researchCaseDetailLoading && !researchCaseDetailError && researchCaseDetail ? (
              <>
                <div className="research-case-detail-header">
                  <div>
                    <h3>{researchCaseDetail.case.title || researchCaseDetail.case.case_id}</h3>
                    <p className="muted">
                      {researchCaseDetail.case.asset_id || '-'} · {researchCaseDetail.case.theme || '-'} ·{' '}
                      {researchCaseDetail.case.status || '-'}
                    </p>
                  </div>
                  <span className="status-chip neutral">{`${researchCaseDetail.summary.evidence_count} evidence`}</span>
                </div>
                <div className="research-source-trace">
                  <span>{researchCaseDetail.case.source_type || '-'}</span>
                  <strong>{researchCaseDetail.case.source_id || '-'}</strong>
                </div>
                {(researchCaseDetail.gap_reasons?.length || researchCaseDetail.gap_summary) ? (
                  <div className="research-source-trace">
                    <span>Gap</span>
                    <strong>
                      {researchCaseDetail.gap_reasons?.length
                        ? researchCaseDetail.gap_reasons.map(gapReasonLabel).join(' / ')
                        : researchCaseDetail.gap_summary}
                    </strong>
                  </div>
                ) : null}
                <div className="research-detail-columns">
                  <div>
                    <h4>Claims</h4>
                    {researchCaseDetail.claims.length === 0 ? <p className="muted">暂无 claims。</p> : null}
                    {researchCaseDetail.claims.map((claim) => (
                      <div className="research-detail-row" key={claim.claim_id}>
                        <strong>{claim.claim_type}</strong>
                        <span>{claim.claim_text}</span>
                        <small>{`${claim.source_type || '-'} · ${claim.source_id || '-'}`}</small>
                      </div>
                    ))}
                  </div>
                  <div>
                    <h4>Evidence</h4>
                    {researchCaseDetail.evidence.length === 0 ? <p className="muted">暂无 linked evidence。</p> : null}
                    {researchCaseDetail.evidence.map((evidence) => {
                      const meta = metadataText(evidence.allowed_metadata);
                      return (
                        <div className="research-detail-row" key={`${evidence.evidence_id}:${evidence.target_type}:${evidence.target_id}`}>
                          <strong>{evidence.title || evidence.evidence_id}</strong>
                          <span>{`${evidence.relation || '-'} · ${evidence.target_type || '-'}`}</span>
                          <small>{`${evidence.source_type || '-'} · ${evidence.source_id || '-'}`}</small>
                          {meta ? <small>{meta}</small> : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
                <div className="research-review-actions" aria-label="人工审阅动作">
                  <div className="research-review-actions-heading">
                    <div>
                      <h4>人工审阅动作</h4>
                      <p className="muted">当前状态：{reviewStatusLabel(researchCaseDetail.review_status)}</p>
                    </div>
                    <span className="status-chip neutral">{reviewStatusLabel(researchCaseDetail.review_status)}</span>
                  </div>
                  <div className="research-source-trace">
                    <span>当前状态</span>
                    <strong>{reviewStatusLabel(researchCaseDetail.review_status)}</strong>
                  </div>
                  {researchCaseDetail.latest_review_action ? (
                    <div className="research-source-trace">
                      <span>Latest Action</span>
                      <strong>
                        {reviewActionLabel(researchCaseDetail.latest_review_action.action_type)}
                        {researchCaseDetail.latest_review_action.comment
                          ? ` · ${researchCaseDetail.latest_review_action.comment}`
                          : ''}
                      </strong>
                    </div>
                  ) : null}
                  <label className="research-review-comment">
                    <span>审阅备注</span>
                    <textarea
                      aria-label="审阅备注"
                      value={reviewActionComment}
                      onChange={(event) => setReviewActionComment(event.target.value)}
                      rows={3}
                    />
                  </label>
                  <div className="research-review-action-buttons">
                    {[
                      ['acknowledge_gap', '已知晓缺口'],
                      ['request_more_evidence', '需要补充证据'],
                      ['mark_reviewed', '标记已审阅'],
                      ['defer', '暂缓处理']
                    ].map(([actionType, label]) => (
                      <button
                        type="button"
                        key={actionType}
                        disabled={reviewActionSubmitting !== null}
                        onClick={() => submitReviewAction(actionType)}
                      >
                        {reviewActionSubmitting === actionType ? '写入中...' : label}
                      </button>
                    ))}
                  </div>
                  {reviewActionError ? <p className="error-text">{reviewActionError}</p> : null}
                  <div className="research-review-history" aria-label="审阅动作历史">
                    <h4>审阅动作历史</h4>
                    {(researchCaseDetail.review_actions ?? []).length === 0 ? <p className="muted">暂无审阅动作。</p> : null}
                    {(researchCaseDetail.review_actions ?? []).slice(0, 5).map((action) => (
                      <div className="research-detail-row" key={action.review_action_id}>
                        <strong>{reviewActionLabel(action.action_type)}</strong>
                        <span>{action.comment || '-'}</span>
                        <small>{`${action.reviewer || 'operator'} · ${action.created_at || '-'}`}</small>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : null}
          </div>
        ) : null}
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
            const health = publicationHealth(metrics.contractStatus);
            return (
              <article className="strategy-command-card" data-strategy-id={strategy.strategy_id} key={strategy.strategy_id}>
                <div className="strategy-command-card-header">
                  <strong>{strategy.strategy_name}</strong>
                  {strategyVersionLabel(metrics.strategyVersion) ? (
                    <span className="status-chip neutral">{strategyVersionLabel(metrics.strategyVersion)}</span>
                  ) : null}
                  <span className="status-chip neutral">{statusLabel(metrics.status)}</span>
                </div>
                <div className="strategy-metric-grid">
                  <div>
                    <span>累计收益</span>
                    <strong className={metricClass(metrics.totalReturnPct)} data-testid="strategy-total-return">
                      {formatPercent(metrics.totalReturnPct, { signed: true, fractionDigits: 2 })}
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
                <div className="strategy-card-footer" aria-label={`${strategy.strategy_name} 策略数据状态`}>
                  <strong>{health.label}</strong>
                  <span>{health.detail}</span>
                </div>
                {metrics.isLhbPolicy ? <p className="muted">Top5 先选后校验，不补位</p> : null}
                <div className="strategy-card-footer">
                  <span>
                    截至{' '}
                    <span data-testid="strategy-performance-date">{metrics.asOfDate ?? '-'}</span>
                  </span>
                  <span>{signalLabel(metrics)}</span>
                </div>
                {metrics.contractStatus === 'success' ? <p>{metrics.evidence || strategy.description}</p> : null}
                <button type="button" onClick={() => onOpenStrategy?.(strategy.strategy_id)}>
                  查看 {strategy.strategy_name} 复盘
                </button>
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
