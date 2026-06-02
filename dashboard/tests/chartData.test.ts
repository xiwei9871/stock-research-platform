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

  it('converts intraday timestamps to Unix seconds', () => {
    const result = toCandlestickData([
      { time: '2026-05-29 09:30:00', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }
    ]);

    expect(typeof result[0].time).toBe('number');
    expect(result[0].time).toBe(1780018200);
  });

  it('drops rows with invalid chart times', () => {
    const candles = toCandlestickData([
      { time: 'not-a-date', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 },
      { time: '2026-05-29', open: 11, high: 12, low: 10, close: 11.5, volume: 200, amount: 2000 }
    ]);
    const volumes = toVolumeData([
      { time: 'not-a-date', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 },
      { time: '2026-05-29', open: 11, high: 12, low: 10, close: 11.5, volume: 200, amount: 2000 }
    ]);

    expect(candles).toEqual([{ time: '2026-05-29', open: 11, high: 12, low: 10, close: 11.5 }]);
    expect(volumes).toEqual([{ time: '2026-05-29', value: 200, color: '#1f9d55' }]);
  });
});
