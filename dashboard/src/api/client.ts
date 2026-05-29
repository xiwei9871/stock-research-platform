import type { BarPoint, DashboardOverview, ScoreRow, WatchlistSignalRow } from './types';

type OverviewParams = {
  tradeDate: string;
  scoreVersion: string;
  watchlistId: string;
  topN: number;
};

export async function fetchOverview(params: OverviewParams): Promise<DashboardOverview> {
  return getJson(
    `/api/dashboard/overview?trade_date=${encodeURIComponent(params.tradeDate)}` +
      `&score_version=${encodeURIComponent(params.scoreVersion)}` +
      `&watchlist_id=${encodeURIComponent(params.watchlistId)}` +
      `&top_n=${params.topN}`
  );
}

export async function fetchDailyBars(
  assetId: string,
  startDate: string,
  endDate: string,
  adjustType = 'qfq'
): Promise<BarPoint[]> {
  const payload = await getJson<{ items: BarPoint[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/bars?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&adjust_type=${encodeURIComponent(adjustType)}`
  );
  return payload.items;
}

export async function fetchAssetScore(
  assetId: string,
  tradeDate: string,
  scoreVersion = 'manual_v1'
): Promise<ScoreRow | null> {
  const payload = await getJson<{ item: ScoreRow | null }>(
    `/api/assets/${encodeURIComponent(assetId)}/scores?trade_date=${encodeURIComponent(tradeDate)}` +
      `&score_version=${encodeURIComponent(scoreVersion)}`
  );
  return payload.item;
}

export async function fetchAssetSignals(assetId: string, tradeDate: string): Promise<WatchlistSignalRow[]> {
  const payload = await getJson<{ items: WatchlistSignalRow[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/signals?trade_date=${encodeURIComponent(tradeDate)}`
  );
  return payload.items;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}
