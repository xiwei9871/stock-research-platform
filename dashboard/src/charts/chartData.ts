import type { Time, UTCTimestamp } from 'lightweight-charts';
import type { BarPoint } from '../api/types';

const DAILY_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIME_WITHOUT_ZONE_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

export type CandlePoint = {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type VolumePoint = {
  time: Time;
  value: number;
  color: string;
};

export type AlignedPriceVolumeData = {
  candles: CandlePoint[];
  volumes: VolumePoint[];
  detailsByTimeKey: Map<string, { amount: number | null }>;
  chartPointCount: number;
};

function normalizeTime(input: string): Time | null {
  if (DAILY_DATE_PATTERN.test(input)) {
    return input;
  }

  const normalized = input.replace(' ', 'T');
  // Backend intraday bars without a timezone are China exchange local time.
  const parseTarget = TIME_WITHOUT_ZONE_PATTERN.test(normalized) ? `${normalized}+08:00` : normalized;
  const milliseconds = Date.parse(parseTarget);

  if (Number.isNaN(milliseconds)) {
    return null;
  }

  return Math.floor(milliseconds / 1000) as UTCTimestamp;
}

type TimeResolver = (point: BarPoint, index: number) => Time | null;

export function toCandlestickData(points: BarPoint[], resolveTime: TimeResolver = (point) => normalizeTime(point.time)): CandlePoint[] {
  return points
    .map((point, index) => {
      const time = resolveTime(point, index);

      if (time === null || point.open === null || point.high === null || point.low === null || point.close === null) {
        return null;
      }

      return {
        time,
        open: point.open,
        high: point.high,
        low: point.low,
        close: point.close
      };
    })
    .filter((point): point is CandlePoint => point !== null);
}

export function toVolumeData(points: BarPoint[], resolveTime: TimeResolver = (point) => normalizeTime(point.time)): VolumePoint[] {
  return points
    .map((point, index) => {
      const time = resolveTime(point, index);

      if (time === null || point.volume === null || point.open === null || point.close === null) {
        return null;
      }

      return {
        time,
        value: point.volume,
        color: point.close >= point.open ? '#d64545' : '#1f9d55'
      };
    })
    .filter((point): point is VolumePoint => point !== null);
}

export function toAlignedPriceVolumeData(
  points: BarPoint[],
  resolveTime: TimeResolver = (point) => normalizeTime(point.time)
): AlignedPriceVolumeData {
  const candles: CandlePoint[] = [];
  const volumes: VolumePoint[] = [];
  const detailsByTimeKey = new Map<string, { amount: number | null }>();

  points.forEach((point, index) => {
    const time = resolveTime(point, index);
    if (
      time === null ||
      point.open === null ||
      point.high === null ||
      point.low === null ||
      point.close === null ||
      point.volume === null
    ) {
      return;
    }

    candles.push({
      time,
      open: point.open,
      high: point.high,
      low: point.low,
      close: point.close
    });
    volumes.push({
      time,
      value: point.volume,
      color: point.close >= point.open ? '#d64545' : '#1f9d55'
    });
    detailsByTimeKey.set(String(time), {
      amount: point.amount
    });
  });

  return {
    candles,
    volumes,
    detailsByTimeKey,
    chartPointCount: candles.length
  };
}
