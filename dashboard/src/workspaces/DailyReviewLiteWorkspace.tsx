import { DailyReviewLitePage } from '../pages/DailyReviewLitePage';

export function DailyReviewLiteWorkspace() {
  return <DailyReviewLitePage initialTradeDate={readTradeDateFromUrl()} />;
}

function readTradeDateFromUrl() {
  if (typeof window === 'undefined') {
    return undefined;
  }

  const value = new URLSearchParams(window.location.search).get('trade_date');
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;
}
