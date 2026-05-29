import type { BarPoint } from '../api/types';

export type CandlePoint = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type VolumePoint = {
  time: string;
  value: number;
  color: string;
};

export function toCandlestickData(points: BarPoint[]): CandlePoint[] {
  return points
    .filter((point) => point.open !== null && point.high !== null && point.low !== null && point.close !== null)
    .map((point) => ({
      time: point.time,
      open: point.open as number,
      high: point.high as number,
      low: point.low as number,
      close: point.close as number
    }));
}

export function toVolumeData(points: BarPoint[]): VolumePoint[] {
  return points
    .filter((point) => point.volume !== null && point.open !== null && point.close !== null)
    .map((point) => ({
      time: point.time,
      value: point.volume as number,
      color: (point.close as number) >= (point.open as number) ? '#1f9d55' : '#d64545'
    }));
}
