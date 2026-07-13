import type {
  TechBottleneckReviewDecisionPayload,
  TechBottleneckReviewDecisionResponse,
  TechBottleneckReviewDecisionSummary,
  TechBottleneckReviewDecisionsResponse,
  TechBottleneckReviewEvidenceResponse,
  TechBottleneckReviewFilterOptions,
  TechBottleneckReviewSourceResponse,
  TechBottleneckReviewStock,
  TechBottleneckReviewStockParams,
  TechBottleneckReviewStocksResponse,
  TechBottleneckReviewSummary
} from '../types/techBottleneckReview';

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = window.localStorage.getItem('dashboardWriteToken') ?? '';
  if (token) {
    headers['X-Dashboard-Write-Token'] = token;
  }
  const response = await fetch(path, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      detail = `${response.status}`;
    }
    throw new Error(`POST ${path} failed: ${detail}`);
  }
  return response.json() as Promise<T>;
}

function queryString(params: TechBottleneckReviewStockParams = {}) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    searchParams.set(key, String(value));
  });
  const query = searchParams.toString();
  return query ? `?${query}` : '';
}

export function fetchTechBottleneckReviewUniverseSummary(): Promise<TechBottleneckReviewSummary> {
  return getJson<TechBottleneckReviewSummary>('/api/research/tech-bottleneck/review-universe/summary');
}

export function fetchTechBottleneckReviewUniverseStocks(
  params: TechBottleneckReviewStockParams = {}
): Promise<TechBottleneckReviewStocksResponse> {
  return getJson<TechBottleneckReviewStocksResponse>(`/api/research/tech-bottleneck/review-universe/stocks${queryString(params)}`);
}

export function fetchTechBottleneckReviewUniverseStock(stockCode: string): Promise<TechBottleneckReviewStock> {
  return getJson<TechBottleneckReviewStock>(`/api/research/tech-bottleneck/review-universe/stocks/${stockCode}`);
}

export function fetchTechBottleneckReviewUniverseEvidence(stockCode: string): Promise<TechBottleneckReviewEvidenceResponse> {
  return getJson<TechBottleneckReviewEvidenceResponse>(`/api/research/tech-bottleneck/review-universe/stocks/${stockCode}/evidence`);
}

export function fetchTechBottleneckReviewUniverseSources(stockCode: string): Promise<TechBottleneckReviewSourceResponse> {
  return getJson<TechBottleneckReviewSourceResponse>(`/api/research/tech-bottleneck/review-universe/stocks/${stockCode}/sources`);
}

export function fetchTechBottleneckReviewUniverseFilterOptions(): Promise<TechBottleneckReviewFilterOptions> {
  return getJson<TechBottleneckReviewFilterOptions>('/api/research/tech-bottleneck/review-universe/filter-options');
}

export function fetchTechBottleneckReviewUniverseDecisionSummary(): Promise<TechBottleneckReviewDecisionSummary> {
  return getJson<TechBottleneckReviewDecisionSummary>('/api/research/tech-bottleneck/review-universe/decision-summary');
}

export function fetchTechBottleneckReviewUniverseDecisions(stockCode: string, limit = 5): Promise<TechBottleneckReviewDecisionsResponse> {
  const query = new URLSearchParams({ stock_code: stockCode, limit: String(limit) }).toString();
  return getJson<TechBottleneckReviewDecisionsResponse>(`/api/research/tech-bottleneck/review-universe/decisions?${query}`);
}

export function createTechBottleneckReviewUniverseDecision(
  payload: TechBottleneckReviewDecisionPayload
): Promise<TechBottleneckReviewDecisionResponse> {
  return postJson<TechBottleneckReviewDecisionResponse>('/api/research/tech-bottleneck/review-universe/decisions', payload);
}
