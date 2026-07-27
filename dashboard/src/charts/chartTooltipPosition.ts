export type ChartTooltipPositionInput = {
  pointerX: number;
  pointerY: number;
  containerWidth: number;
  containerHeight: number;
  tooltipWidth: number;
  tooltipHeight: number;
  gap?: number;
  margin?: number;
  verticalOffset?: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function resolveChartTooltipPosition({
  pointerX,
  pointerY,
  containerWidth,
  containerHeight,
  tooltipWidth,
  tooltipHeight,
  gap = 14,
  margin = 12,
  verticalOffset = 82
}: ChartTooltipPositionInput) {
  const rightCandidate = pointerX + gap;
  const leftCandidate = pointerX - gap - tooltipWidth;
  const preferredLeft = rightCandidate + tooltipWidth <= containerWidth - margin
    ? rightCandidate
    : leftCandidate;
  const maxLeft = Math.max(margin, containerWidth - tooltipWidth - margin);
  const maxTop = Math.max(margin, containerHeight - tooltipHeight - margin);

  return {
    left: clamp(preferredLeft, margin, maxLeft),
    top: clamp(pointerY - verticalOffset, margin, maxTop)
  };
}
