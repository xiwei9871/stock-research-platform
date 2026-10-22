import type {
  CompanyIntelligenceDossier,
  CompanyIntelligenceDossierListResponse,
  CompanyIntelligenceReviewRecord
} from '../types/companyIntelligence';

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

export function fetchCompanyIntelligenceDossiers(): Promise<CompanyIntelligenceDossierListResponse> {
  return getJson('/api/research/company-intelligence/dossiers');
}

export function fetchCompanyIntelligenceDossier(stockCode: string): Promise<CompanyIntelligenceDossier> {
  return getJson(`/api/research/company-intelligence/stocks/${encodeURIComponent(stockCode)}/dossier`);
}

export function fetchCompanyIntelligenceReviews(stockCode: string): Promise<{ items: CompanyIntelligenceReviewRecord[] }> {
  return getJson(`/api/research/company-intelligence/stocks/${encodeURIComponent(stockCode)}/reviews`);
}

export function recordCompanyIntelligenceReview(
  stockCode: string,
  payload: { claim_id: string; review_status: string; reviewer: string; comment: string; dimension?: string }
): Promise<CompanyIntelligenceReviewRecord> {
  return postJson(`/api/research/company-intelligence/stocks/${encodeURIComponent(stockCode)}/reviews`, payload);
}

export function companyIntelligenceMarkdownUrl(stockCode: string): string {
  return `/api/research/company-intelligence/stocks/${encodeURIComponent(stockCode)}/dossier.md`;
}
