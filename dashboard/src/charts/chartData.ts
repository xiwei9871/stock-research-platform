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
