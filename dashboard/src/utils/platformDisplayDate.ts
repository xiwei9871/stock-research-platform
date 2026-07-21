type ReadinessDateSource = {
  display_trade_date?: string | null;
  latest_market_date?: string | null;
  latest_trade_date?: string | null;
};

function firstDate(...dates: Array<string | null | undefined>) {
  return dates.map((date) => date?.trim()).find(Boolean) ?? '';
}

export function resolvePlatformDisplayDate(
  readiness: ReadinessDateSource | null,
  ...legacyFallbackDates: Array<string | null | undefined>
) {
  if (readiness && Object.prototype.hasOwnProperty.call(readiness, 'display_trade_date')) {
    return firstDate(readiness.display_trade_date);
  }
  return firstDate(
    readiness?.latest_market_date,
    readiness?.latest_trade_date,
    ...legacyFallbackDates
  );
}
