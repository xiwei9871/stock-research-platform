import { describe, expect, it } from 'vitest';
import { toCandlestickData, toVolumeData } from '../src/charts/chartData';

describe('chart data conversion', () => {
  it('drops rows without complete OHLC values', () => {
    const result = toCandlestickData([
      { time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 },
      { time: '2026-05-29', open: null, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }
    ]);

    expect(result).toEqual([{ time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5 }]);
  });

  it('maps volume color from close versus open', () => {
    const result = toVolumeData([
      { time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 },
      { time: '2026-05-29', open: 10, high: 10.5, low: 9, close: 9.5, volume: 200, amount: 1000 }
    ]);

    expect(result[0].color).toBe('#1f9d55');
    expect(result[1].color).toBe('#d64545');
  });
});
