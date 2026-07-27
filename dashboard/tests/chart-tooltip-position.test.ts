import { describe, expect, it } from 'vitest';
import { resolveChartTooltipPosition } from '../src/charts/chartTooltipPosition';

describe('resolveChartTooltipPosition', () => {
  it('keeps the tooltip to the right of a centered pointer', () => {
    expect(resolveChartTooltipPosition({
      pointerX: 300,
      pointerY: 180,
      containerWidth: 800,
      containerHeight: 460,
      tooltipWidth: 180,
      tooltipHeight: 110
    })).toEqual({ left: 314, top: 98 });
  });

  it('flips the tooltip to the left at the right edge', () => {
    expect(resolveChartTooltipPosition({
      pointerX: 760,
      pointerY: 180,
      containerWidth: 800,
      containerHeight: 460,
      tooltipWidth: 180,
      tooltipHeight: 110
    })).toEqual({ left: 566, top: 98 });
  });

  it('clamps the tooltip at every container edge', () => {
    expect(resolveChartTooltipPosition({
      pointerX: 4,
      pointerY: 4,
      containerWidth: 200,
      containerHeight: 120,
      tooltipWidth: 190,
      tooltipHeight: 100
    })).toEqual({ left: 12, top: 12 });
  });
});
