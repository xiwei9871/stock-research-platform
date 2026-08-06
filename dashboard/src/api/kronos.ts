export type KronosRunStatus = 'queued' | 'running' | 'partial' | 'succeeded' | 'failed';
export type KronosForecastPeriodKey = 'daily' | 'intraday' | '10m' | '20m' | '30m';

export type KronosBar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number;
};

export type KronosForecastPeriod = {
  sample_count?: number;
  horizon?: number;
  representative_path?: KronosBar[];
  p10?: number[];
  p50?: number[];
  p90?: number[];
  summary?: {
    close?: { p10?: number[]; p50?: number[]; p90?: number[] };
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

export type KronosPredictionResult = {
  status?: string;
  sample_count?: number;
  daily?: KronosForecastPeriod | null;
  intraday?: KronosForecastPeriod | null;
  aggregated?: Partial<Record<'10m' | '20m' | '30m', KronosForecastPeriod>>;
  diagnostics?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type KronosPeriodState = {
  status: 'succeeded' | 'insufficient_data' | 'failed' | string;
  data_as_of?: string | null;
  row_count?: number;
  source?: string | null;
  quality?: string | null;
  error?: string | null;
  [key: string]: unknown;
};

export type KronosRun = {
  run_id: string;
  code: string;
  status: KronosRunStatus;
  created_at: string;
  updated_at: string;
  snapshot?: {
    data_as_of?: string | null;
    daily?: { data_as_of?: string | null; row_count?: number; source?: string | null };
    intraday?: { data_as_of?: string | null; row_count?: number; source?: string | null };
    [key: string]: unknown;
  };
  periods?: Partial<Record<'daily' | 'intraday', KronosPeriodState>>;
  result?: KronosPredictionResult | null;
  diagnostics?: Array<Record<string, unknown>>;
  error?: string | null;
  [key: string]: unknown;
};

export type KronosPredictionOptions = {
  force?: boolean;
  model?: string;
  sample_count?: number;
  daily_horizon?: number;
  intraday_horizon?: number;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? String(body.detail) : null;
    throw new Error(detail || `Kronos请求失败 (${response.status})`);
  }
  return body as T;
}

function assetPath(assetId: string) {
  return encodeURIComponent(String(assetId || '').trim());
}

export function createKronosPrediction(
  assetId: string,
  options: KronosPredictionOptions = {}
): Promise<KronosRun> {
  const { force, ...body } = options;
  const query = force ? '?force=true' : '';
  return requestJson<KronosRun>(`/api/assets/${assetPath(assetId)}/kronos/predictions${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export function fetchKronosRun(runId: string): Promise<KronosRun> {
  return requestJson<KronosRun>(`/api/kronos/runs/${encodeURIComponent(runId)}`);
}

export function fetchLatestKronosPrediction(assetId: string): Promise<KronosRun> {
  return requestJson<KronosRun>(`/api/assets/${assetPath(assetId)}/kronos/predictions/latest`);
}

