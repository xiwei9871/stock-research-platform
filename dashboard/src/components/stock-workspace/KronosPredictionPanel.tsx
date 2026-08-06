import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { BarPoint } from '../../api/types';
import {
  createKronosPrediction,
  fetchLatestKronosPrediction,
  fetchKronosRun,
  type KronosForecastPeriod,
  type KronosForecastPeriodKey,
  type KronosPredictionResult,
  type KronosRun,
  type KronosRunStatus
} from '../../api/kronos';
import { KronosPredictionChart } from './KronosPredictionChart';

const PERIODS: Array<{ key: KronosForecastPeriodKey; label: string }> = [
  { key: 'daily', label: '日K' },
  { key: 'intraday', label: '5分钟' },
  { key: '10m', label: '10分钟' },
  { key: '20m', label: '20分钟' },
  { key: '30m', label: '30分钟' }
];

type KronosPredictionPanelProps = {
  assetId: string;
  historyBars?: BarPoint[];
  onDailyForecastChange?: (forecast: KronosForecastPeriod | null) => void;
  showHistory?: boolean;
};

function normalizeCode(value: string) {
  const text = String(value || '').trim().toUpperCase();
  const match = text.match(/\d{6}/);
  return match?.[0] ?? text;
}

function getForecastPeriod(result: KronosPredictionResult | null | undefined, key: KronosForecastPeriodKey) {
  if (!result) return null;
  if (key === 'daily') return result.daily ?? null;
  if (key === 'intraday') return result.intraday ?? null;
  return result.aggregated?.[key] ?? null;
}

function isAvailable(period: KronosForecastPeriod | null) {
  return Boolean(period?.representative_path?.length);
}

function hasPredictionResult(run: KronosRun) {
  return Boolean(run.result && (isAvailable(run.result.daily ?? null) || isAvailable(run.result.intraday ?? null)));
}

function statusText(status: KronosRunStatus | 'idle') {
  const labels: Record<KronosRunStatus | 'idle', string> = {
    idle: '等待预测',
    queued: '排队中',
    running: '预测中',
    partial: '部分完成',
    succeeded: '已完成',
    failed: '失败'
  };
  return labels[status];
}

function statusClass(status: KronosRunStatus | 'idle') {
  if (status === 'succeeded') return 'success';
  if (status === 'partial') return 'warning';
  if (status === 'failed') return 'danger';
  return 'neutral';
}

function asOf(run: KronosRun | null) {
  return (
    run?.snapshot?.data_as_of ??
    run?.snapshot?.daily?.data_as_of ??
    run?.snapshot?.intraday?.data_as_of ??
    ''
  );
}

function diagnosticsFromRun(run: KronosRun | null) {
  const values = (run?.diagnostics ?? [])
    .map((item) => item.message ?? item.warning ?? item.error ?? item.status)
    .filter(Boolean)
    .map(String);
  return Array.from(new Set(values)).slice(0, 5);
}

export function KronosPredictionPanel({
  assetId,
  historyBars = [],
  onDailyForecastChange,
  showHistory = false
}: KronosPredictionPanelProps) {
  const [status, setStatus] = useState<KronosRunStatus | 'idle'>('idle');
  const [run, setRun] = useState<KronosRun | null>(null);
  const [forecastPeriod, setForecastPeriod] = useState<KronosForecastPeriodKey>('daily');
  const [diagnostics, setDiagnostics] = useState<string[]>([]);
  const [retrying, setRetrying] = useState(false);
  const generationRef = useRef(0);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const applyRun = useCallback((nextRun: KronosRun) => {
    setRun(nextRun);
    setStatus(nextRun.status);
    setDiagnostics(diagnosticsFromRun(nextRun));
  }, []);

  const pollRun = useCallback(
    async (runId: string, generation: number) => {
      if (generation !== generationRef.current) return;
      try {
        const nextRun = await fetchKronosRun(runId);
        if (generation !== generationRef.current) return;
        applyRun(nextRun);
        if (nextRun.status === 'queued' || nextRun.status === 'running') {
          pollTimerRef.current = setTimeout(() => void pollRun(runId, generation), 1500);
        } else {
          clearPolling();
        }
      } catch (error: unknown) {
        if (generation !== generationRef.current) return;
        clearPolling();
        setStatus('failed');
        setDiagnostics([error instanceof Error ? error.message : String(error)]);
      }
    },
    [applyRun, clearPolling]
  );

  const startPrediction = useCallback(
    async (force: boolean) => {
      const code = normalizeCode(assetId);
      const generation = generationRef.current + 1;
      generationRef.current = generation;
      clearPolling();
      setRetrying(force);
      setRun(null);
      setStatus('queued');
      setDiagnostics([]);

      if (!/^\d{6}$/.test(code)) {
        setStatus('idle');
        setDiagnostics(['Kronos预测目前仅支持6位A股代码']);
        setRetrying(false);
        return;
      }

      try {
        if (!force) {
          try {
            const cachedRun = await fetchLatestKronosPrediction(code);
            if (generation !== generationRef.current) return;
            if (hasPredictionResult(cachedRun)) {
              applyRun(cachedRun);
              return;
            }
            if (cachedRun.status === 'queued' || cachedRun.status === 'running') {
              applyRun(cachedRun);
              pollTimerRef.current = setTimeout(() => void pollRun(cachedRun.run_id, generation), 1500);
              return;
            }
          } catch {
            // A missing or unavailable cached run falls through to a new prediction request.
          }
        }

        const nextRun = await createKronosPrediction(code, { force });
        if (generation !== generationRef.current) return;
        applyRun(nextRun);
        if (nextRun.status === 'queued' || nextRun.status === 'running') {
          pollTimerRef.current = setTimeout(() => void pollRun(nextRun.run_id, generation), 1500);
        }
      } catch (error: unknown) {
        if (generation !== generationRef.current) return;
        setStatus('failed');
        setDiagnostics([error instanceof Error ? error.message : String(error)]);
      } finally {
        if (generation === generationRef.current) setRetrying(false);
      }
    },
    [applyRun, assetId, clearPolling, pollRun]
  );

  useEffect(() => {
    void startPrediction(false);
    return () => {
      generationRef.current += 1;
      clearPolling();
    };
  }, [assetId, clearPolling, startPrediction]);

  const availablePeriods = useMemo(
    () => PERIODS.filter((item) => isAvailable(getForecastPeriod(run?.result, item.key))).map((item) => item.key),
    [run?.result]
  );

  useEffect(() => {
    if (availablePeriods.length > 0 && !availablePeriods.includes(forecastPeriod)) {
      setForecastPeriod(availablePeriods[0]);
    }
  }, [availablePeriods, forecastPeriod]);

  const selectedForecast = getForecastPeriod(run?.result, forecastPeriod);
  const selectedLabel = PERIODS.find((item) => item.key === forecastPeriod)?.label ?? forecastPeriod;
  const dailyForecast = getForecastPeriod(run?.result, 'daily');

  useEffect(() => {
    onDailyForecastChange?.(dailyForecast);
  }, [dailyForecast, onDailyForecastChange]);

  return (
    <section className="workspace-band kronos-panel" role="region" aria-label="Kronos预测">
      <div className="section-heading">
        <div>
          <h3>Kronos预测</h3>
          <p className="muted">
            {asOf(run) ? `数据截至 ${asOf(run)}` : '自动预测未来10根日K和48根5分钟K线'}
            {run?.result?.sample_count ? ` · ${run.result.sample_count}条采样路径` : ''}
          </p>
        </div>
        <div className="kronos-panel-actions">
          <span className={`status-chip ${statusClass(status)}`}>{statusText(status)}</span>
          <button
            type="button"
            className="secondary-button"
            disabled={retrying || status === 'queued' || status === 'running'}
            onClick={() => void startPrediction(true)}
          >
            {retrying ? '重新预测中…' : '重新预测'}
          </button>
        </div>
      </div>

      <div className="segmented-control kronos-period-control" role="group" aria-label="Kronos预测周期">
        {PERIODS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={forecastPeriod === item.key ? 'active' : ''}
            aria-pressed={forecastPeriod === item.key}
            disabled={!availablePeriods.includes(item.key)}
            onClick={() => setForecastPeriod(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="kronos-period-statuses">
        {PERIODS.map((item) => (
          <span key={item.key}>
            {item.label}：{availablePeriods.includes(item.key) ? '可用' : status === 'failed' ? '失败/数据不足' : '等待结果'}
          </span>
        ))}
      </div>

      {diagnostics.map((message) => (
        <p className="muted kronos-diagnostic" key={message}>
          {message}
        </p>
      ))}
      {selectedForecast && isAvailable(selectedForecast) ? (
        <>
          <p className="muted kronos-forecast-hint">
            {forecastPeriod === 'daily' && showHistory
              ? '紫色为预测代表路径，虚线为P10/P50/P90收盘区间。'
              : `${selectedLabel}为预测专用视图，不拼接其他粒度历史K线。`}
          </p>
          <KronosPredictionChart
            historyBars={historyBars}
            forecast={selectedForecast}
            overlayHistory={forecastPeriod === 'daily' && showHistory}
          />
        </>
      ) : status === 'succeeded' || status === 'partial' ? (
        <p className="muted">当前周期没有可展示的代表性预测路径。</p>
      ) : null}
    </section>
  );
}
