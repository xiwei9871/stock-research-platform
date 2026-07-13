import type {
  TechnologyIndustryCatalogIndex,
  TechnologyIndustryChainDetail
} from '../types/technologyIndustryCatalog';

const BASE_PATH = '/api/research/technology-industry-catalog';

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    let detail = `request_failed_${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
    } catch {
      detail = `request_failed_${response.status}`;
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function fetchTechnologyIndustryCatalog(): Promise<TechnologyIndustryCatalogIndex> {
  return getJson<TechnologyIndustryCatalogIndex>(BASE_PATH);
}

export function fetchTechnologyIndustryChain(
  chainId: string
): Promise<TechnologyIndustryChainDetail> {
  return getJson<TechnologyIndustryChainDetail>(
    `${BASE_PATH}/chains/${encodeURIComponent(chainId)}`
  );
}
