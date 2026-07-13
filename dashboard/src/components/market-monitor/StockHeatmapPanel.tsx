import { useEffect, useMemo, useRef } from 'react';
import type { StockHeatmapGroup, StockHeatmapPayload, StockHeatmapStock } from '../../api/types';

type StockHeatmapPanelProps = {
  payload: StockHeatmapPayload | null;
  loading: boolean;
  error: string | null;
  onSelectStock: (assetId: string) => void;
};

type Bounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type StockRect = Bounds & {
  stock: StockHeatmapStock;
};

type TreemapInput<T> = {
  item: T;
  value: number;
};

function formatSignedPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatAmountYi(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-';
  return `${(value / 100000000).toFixed(2)}亿`;
}

function colorForChange(value: number | null) {
  const change = value ?? 0;
  const strength = Math.abs(change);
  if (change > 0) {
    if (strength >= 0.05) return '#7f1d1d';
    if (strength >= 0.03) return '#991b1b';
    if (strength >= 0.015) return '#b91c1c';
    return '#dc2626';
  }
  if (change < 0) {
    if (strength >= 0.05) return '#052e16';
    if (strength >= 0.03) return '#14532d';
    if (strength >= 0.015) return '#166534';
    return '#15803d';
  }
  return '#475569';
}

function sortTreemapItems<T>(items: TreemapInput<T>[]) {
  return [...items].filter((entry) => entry.value > 0).sort((left, right) => right.value - left.value);
}

function totalValue<T>(items: TreemapInput<T>[]) {
  return items.reduce((total, entry) => total + entry.value, 0);
}

function splitIndex<T>(items: TreemapInput<T>[]) {
  if (items.length <= 1) return items.length;
  const target = totalValue(items) / 2;
  let cumulative = 0;
  let bestIndex = 1;
  let bestDiff = Number.POSITIVE_INFINITY;
  for (let index = 1; index < items.length; index += 1) {
    cumulative += items[index - 1].value;
    const diff = Math.abs(target - cumulative);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestIndex = index;
    }
  }
  return bestIndex;
}

function inset(bounds: Bounds, gap: number): Bounds {
  const half = gap / 2;
  return {
    x: bounds.x + half,
    y: bounds.y + half,
    width: Math.max(0, bounds.width - gap),
    height: Math.max(0, bounds.height - gap)
  };
}

function binaryTreemap<T>(items: TreemapInput<T>[], bounds: Bounds, gap = 2): Array<Bounds & { item: T }> {
  const sorted = sortTreemapItems(items);

  function layout(entries: TreemapInput<T>[], area: Bounds): Array<Bounds & { item: T }> {
    if (entries.length === 0 || area.width <= 1 || area.height <= 1) return [];
    if (entries.length === 1) {
      return [{ ...inset(area, gap), item: entries[0].item }];
    }

    const index = splitIndex(entries);
    const first = entries.slice(0, index);
    const second = entries.slice(index);
    const firstValue = totalValue(first);
    const ratio = firstValue / Math.max(firstValue + totalValue(second), 1);
    const splitVertical = area.width >= area.height;
    const firstBounds = splitVertical
      ? { x: area.x, y: area.y, width: area.width * ratio, height: area.height }
      : { x: area.x, y: area.y, width: area.width, height: area.height * ratio };
    const secondBounds = splitVertical
      ? { x: area.x + firstBounds.width, y: area.y, width: area.width - firstBounds.width, height: area.height }
      : { x: area.x, y: area.y + firstBounds.height, width: area.width, height: area.height - firstBounds.height };

    return [...layout(first, firstBounds), ...layout(second, secondBounds)];
  }

  return layout(sorted, bounds);
}

function buildStockRects(groups: StockHeatmapGroup[], width: number, height: number) {
  const groupRects = binaryTreemap(
    groups.map((group) => ({ item: group, value: Math.max(group.value ?? 0, 1) })),
    { x: 0, y: 0, width, height },
    4
  );
  const stockRects: StockRect[] = [];

  for (const groupRect of groupRects) {
    const titleHeight = Math.min(28, Math.max(18, groupRect.height * 0.12));
    const childBounds = {
      x: groupRect.x,
      y: groupRect.y + titleHeight,
      width: groupRect.width,
      height: Math.max(0, groupRect.height - titleHeight)
    };
    const childRects = binaryTreemap(
      groupRect.item.children.map((stock) => ({ item: stock, value: Math.max(stock.value ?? stock.amount ?? 0, 1) })),
      childBounds,
      2
    );
    for (const child of childRects) {
      stockRects.push({ ...child, stock: child.item });
    }
  }

  return { groupRects, stockRects };
}

function drawHeatmap(canvas: HTMLCanvasElement, payload: StockHeatmapPayload) {
  const context = canvas.getContext('2d');
  if (!context) return;
  const width = Math.max(1, canvas.clientWidth || 720);
  const height = Math.max(1, canvas.clientHeight || 420);
  const pixelRatio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * pixelRatio);
  canvas.height = Math.floor(height * pixelRatio);
  context.save();
  context.scale(pixelRatio, pixelRatio);
  context.clearRect(0, 0, width, height);
  context.fillStyle = '#f8fafc';
  context.fillRect(0, 0, width, height);

  const { groupRects, stockRects } = buildStockRects(payload.groups, width, height);
  for (const groupRect of groupRects) {
    context.fillStyle = '#e2e8f0';
    context.fillRect(groupRect.x, groupRect.y, groupRect.width, groupRect.height);
    context.fillStyle = '#0f172a';
    context.font = '600 12px system-ui, sans-serif';
    context.fillText(groupRect.item.group_name, groupRect.x + 6, groupRect.y + 16);
  }
  for (const rect of stockRects) {
    context.fillStyle = colorForChange(rect.stock.change_pct);
    context.fillRect(rect.x, rect.y, rect.width, rect.height);
    context.strokeStyle = '#f8fafc';
    context.strokeRect(rect.x, rect.y, rect.width, rect.height);
    if (rect.width >= 52 && rect.height >= 24) {
      context.fillStyle = '#ffffff';
      context.font = '600 11px system-ui, sans-serif';
      context.fillText(rect.stock.name, rect.x + 4, rect.y + 13);
    }
  }
  context.restore();
}

function flattenStocks(payload: StockHeatmapPayload | null) {
  return payload?.groups.flatMap((group) => group.children) ?? [];
}

export function StockHeatmapPanel({ payload, loading, error, onSelectStock }: StockHeatmapPanelProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stocks = useMemo(() => flattenStocks(payload).slice(0, 12), [payload]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !payload || payload.groups.length === 0) return undefined;
    drawHeatmap(canvas, payload);

    const resizeObserver =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => {
            drawHeatmap(canvas, payload);
          })
        : null;
    resizeObserver?.observe(canvas);
    return () => resizeObserver?.disconnect();
  }, [payload]);

  if (loading) {
    return <div className="market-monitor-stock-heatmap-state">个股云图加载中</div>;
  }

  if (error) {
    return <div className="market-monitor-stock-heatmap-state error">{error}</div>;
  }

  if (!payload || payload.groups.length === 0 || payload.summary.stock_count === 0) {
    return <div className="market-monitor-stock-heatmap-state">暂无个股云图数据</div>;
  }

  return (
    <section className="market-monitor-stock-heatmap-panel" aria-label="个股云图">
      <div className="market-monitor-stock-heatmap-summary">
        <span>个股 {payload.summary.stock_count}</span>
        <span>上涨 {payload.summary.up_count}</span>
        <span>下跌 {payload.summary.down_count}</span>
        <span>成交额 {formatAmountYi(payload.summary.total_amount)}</span>
      </div>
      <canvas ref={canvasRef} role="img" aria-label="全市场个股云图" className="market-monitor-stock-heatmap-canvas" />
      <section className="market-monitor-stock-heatmap-list" aria-label="热区个股 Top N">
        {stocks.map((stock) => (
          <button
            key={stock.asset_id}
            type="button"
            aria-label={`打开 ${stock.name}`}
            onClick={() => onSelectStock(stock.asset_id)}
          >
            <strong>{stock.name}</strong>
            <span>{stock.symbol}</span>
            <span>{formatSignedPercent(stock.change_pct)}</span>
            <small>{stock.group_name}</small>
            <small>{formatAmountYi(stock.amount)}</small>
          </button>
        ))}
      </section>
    </section>
  );
}
