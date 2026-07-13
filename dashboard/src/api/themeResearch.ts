import type {
  ThemeResearchClaimCollection,
  ThemeResearchCompanyCollection,
  ThemeResearchNodeCollection,
  ThemeResearchSourceCollection,
  ThemeResearchThemeCollection,
  ThemeResearchThemeDetail
} from '../types/themeResearch';

const BASE_PATH = '/api/research/theme-decomposition/themes';

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

function themePath(themeId: string, suffix = '') {
  return `${BASE_PATH}/${encodeURIComponent(themeId)}${suffix}`;
}

export function fetchThemeResearchThemes(): Promise<ThemeResearchThemeCollection> {
  return getJson<ThemeResearchThemeCollection>(BASE_PATH);
}

export function fetchThemeResearchTheme(themeId: string): Promise<ThemeResearchThemeDetail> {
  return getJson<ThemeResearchThemeDetail>(themePath(themeId));
}

export function fetchThemeResearchNodes(themeId: string): Promise<ThemeResearchNodeCollection> {
  return getJson<ThemeResearchNodeCollection>(themePath(themeId, '/nodes'));
}

export function fetchThemeResearchSources(themeId: string): Promise<ThemeResearchSourceCollection> {
  return getJson<ThemeResearchSourceCollection>(themePath(themeId, '/sources'));
}

export function fetchThemeResearchClaims(themeId: string): Promise<ThemeResearchClaimCollection> {
  return getJson<ThemeResearchClaimCollection>(themePath(themeId, '/claims'));
}

export function fetchThemeResearchCompanies(themeId: string): Promise<ThemeResearchCompanyCollection> {
  return getJson<ThemeResearchCompanyCollection>(themePath(themeId, '/companies'));
}
