export type AssetSummary = {
  asset_id: string;
  symbol: string;
  name: string;
  exchange: string;
  board: string | null;
  is_active: boolean;
};

export type BarPoint = {
  time: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  amount: number | null;
};

export type ScoreRow = {
  trade_date: string;
  asset_id: string;
  rank: number;
  score_total: number;
  score_version: string;
  score_components: Record<string, unknown>;
};

export type WatchlistSignalRow = {
  watchlist_id: string;
  trade_date: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  priority: number;
  signal_score: number | null;
  primary_signal: string;
  signal_tags: string[];
  risk_tags: string[];
  must_watch: boolean;
  reason_json: Record<string, unknown>;
};

export type ReportLink = {
  report_type: string;
  title: string;
  path: string;
  format: string;
  trade_date: string | null;
};

export type DashboardOverview = {
  trade_date: string;
  score_version: string;
  watchlist_id: string;
  top_scores: ScoreRow[];
  watchlist_signals: WatchlistSignalRow[];
  reports: ReportLink[];
};
