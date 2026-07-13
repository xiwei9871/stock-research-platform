import { useEffect, useMemo, useRef, useState } from 'react';
import type { StockMarketContextHeatmapPayload, StockMarketContextPeer } from '../../api/types';

type StockMarketContextHeatmapProps = {
  payload: StockMarketContextHeatmapPayload | null;
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

type PeerRect = Bounds & {
  peer: StockMarketContextPeer;
};

type TreemapInput<T> = {
  item: T;
  value: number;
};

const MAX_PEER_SAMPLE_SIZE = 12;

function formatSignedPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatAmountYi(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-';
  return `${(value / 100000000).toFixed(2)}亿`;
}

function rankLabel(value: number | null) {
  return value == null ? '-' : `#${value}`;
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

function totalValue<T>(items: TreemapInput<T>[]) {
  return items.reduce((total, item) => total + item.value, 0);
}

function sortedItems<T>(items: TreemapInput<T>[]) {
  return [...items].filter((item) => item.value > 0).sort((left, right) => right.value - left.value);
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
  const sorted = sortedItems(items);

  function layout(entries: TreemapInput<T>[], area: Bounds): Array<Bounds & { item: T }> {
    if (entries.length === 0 || area.width <= 1 || area.height <= 1) return [];
    if (entries.length === 1) return [{ ...inset(area, gap), item: entries[0].item }];

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

function buildPeerRects(payload: StockMarketContextHeatmapPayload, width: number, height: number): PeerRect[] {
  const uniquePeers = dedupePeers(payload.peers);
  return binaryTreemap(
    uniquePeers.map((peer) => ({ item: peer, value: Math.max(peer.amount ?? peer.value ?? 0, 1) })),
    { x: 0, y: 0, width, height },
    2
  ).map((rect) => ({ ...rect, peer: rect.item }));
}

function drawHeatmap(canvas: HTMLCanvasElement, payload: StockMarketContextHeatmapPayload) {
  const context = canvas.getContext('2d');
  if (!context) return [];
  const width = Math.max(1, canvas.clientWidth || 460);
  const height = Math.max(1, canvas.clientHeight || 240);
  const pixelRatio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * pixelRatio);
  canvas.height = Math.floor(height * pixelRatio);

  context.save();
  context.scale(pixelRatio, pixelRatio);
  context.clearRect(0, 0, width, height);
  context.fillStyle = '#f8fafc';
  context.fillRect(0, 0, width, height);

  const rects = buildPeerRects(payload, width, height);
  for (const rect of rects) {
    context.fillStyle = colorForChange(rect.peer.change_pct);
    context.fillRect(rect.x, rect.y, rect.width, rect.height);
    context.strokeStyle = rect.peer.is_selected ? '#facc15' : '#f8fafc';
    context.lineWidth = rect.peer.is_selected ? 3 : 1;
    context.strokeRect(rect.x, rect.y, rect.width, rect.height);
    if (rect.width >= 62 && rect.height >= 28) {
      context.fillStyle = '#ffffff';
      context.font = rect.peer.is_selected ? '700 11px system-ui, sans-serif' : '600 11px system-ui, sans-serif';
      drawFittedText(context, rect.peer.name, rect.x + 4, rect.y + 13, rect.width - 8);
    }
  }
  context.restore();
  return rects;
}

function drawFittedText(context: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number) {
  if (maxWidth <= 12) return;
  if (context.measureText(text).width <= maxWidth) {
    context.fillText(text, x, y);
    return;
  }
  const ellipsis = '…';
  let clipped = text;
  while (clipped.length > 1 && context.measureText(`${clipped}${ellipsis}`).width > maxWidth) {
    clipped = clipped.slice(0, -1);
  }
  if (clipped.length > 1) {
    context.fillText(`${clipped}${ellipsis}`, x, y);
  }
}

function findRect(rects: PeerRect[], x: number, y: number) {
  return rects.find((rect) => x >= rect.x && x <= rect.x + rect.width && y >= rect.y && y <= rect.y + rect.height);
}

function dedupePeers(peers: StockMarketContextPeer[]) {
  const seen = new Set<string>();
  return peers.filter((peer) => {
    if (seen.has(peer.asset_id)) {
      return false;
    }
    seen.add(peer.asset_id);
    return true;
  });
}

function peerValue(peer: StockMarketContextPeer) {
  return Math.max(peer.amount ?? peer.value ?? 0, 0);
}

function findSelectedPeer(uniquePeers: StockMarketContextPeer[], selected: StockMarketContextHeatmapPayload['selected']) {
  const selectedAssetId = selected?.asset_id ?? null;
  return (
    uniquePeers.find((peer) => peer.asset_id === selectedAssetId) ??
    uniquePeers.find((peer) => peer.is_selected) ??
    null
  );
}

function buildPeerSampleFromUniverse(uniquePeers: StockMarketContextPeer[]) {
  const rankedPeers = [...uniquePeers].sort((left, right) => peerValue(right) - peerValue(left));
  return dedupePeers(rankedPeers.slice(0, MAX_PEER_SAMPLE_SIZE));
}

export function StockMarketContextHeatmap({ payload, loading, error, onSelectStock }: StockMarketContextHeatmapProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rectsRef = useRef<PeerRect[]>([]);
  const [hoveredPeer, setHoveredPeer] = useState<StockMarketContextPeer | null>(null);
  const peerUniverse = useMemo(() => dedupePeers(payload?.peers ?? []), [payload]);
  const selectedPeer = useMemo(() => (payload ? findSelectedPeer(peerUniverse, payload.selected) : null), [payload, peerUniverse]);
  const samplePeers = useMemo(() => buildPeerSampleFromUniverse(peerUniverse), [peerUniverse]);
  const selectedInSample = Boolean(selectedPeer && samplePeers.some((peer) => peer.asset_id === selectedPeer.asset_id));
  const sampleSummary = useMemo(
    () => ({
      peerCount: peerUniverse.length,
      upCount: peerUniverse.filter((peer) => (peer.change_pct ?? 0) > 0).length,
      downCount: peerUniverse.filter((peer) => (peer.change_pct ?? 0) < 0).length
    }),
    [peerUniverse]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !payload || samplePeers.length === 0) return undefined;
    rectsRef.current = drawHeatmap(canvas, { ...payload, peers: samplePeers });

    const resizeObserver =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => {
            rectsRef.current = drawHeatmap(canvas, { ...payload, peers: samplePeers });
          })
        : null;
    resizeObserver?.observe(canvas);
    return () => resizeObserver?.disconnect();
  }, [payload, samplePeers]);

  if (loading) {
    return <div className="stock-market-context-state">同业热力加载中</div>;
  }

  if (error) {
    return <div className="stock-market-context-state error">{error}</div>;
  }

  if (!payload || peerUniverse.length === 0) {
    return <div className="stock-market-context-state">暂无同业市场定位数据</div>;
  }

  const selected = payload.selected;
  const inspectorPeer = hoveredPeer ?? selectedPeer ?? null;

  return (
    <section className="stock-market-context-heatmap" aria-label="同业市场定位面板">
      <div className="stock-market-context-heatmap-summary">
        <span>{payload.industry?.industry_name ?? '未分组'}</span>
        <span>同业 {sampleSummary.peerCount}</span>
        <span>上涨 {sampleSummary.upCount}</span>
        <span>下跌 {sampleSummary.downCount}</span>
        <span>涨跌排名 {rankLabel(selected?.change_rank ?? null)}</span>
        <span>成交额排名 {rankLabel(selected?.amount_rank ?? null)}</span>
      </div>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label="同业市场定位热力图"
        className="stock-market-context-heatmap-canvas"
        onMouseMove={(event) => {
          const canvas = event.currentTarget;
          const bounds = canvas.getBoundingClientRect();
          const rect = findRect(rectsRef.current, event.clientX - bounds.left, event.clientY - bounds.top);
          setHoveredPeer(rect?.peer ?? null);
        }}
        onMouseLeave={() => setHoveredPeer(null)}
        onClick={(event) => {
          const canvas = event.currentTarget;
          const bounds = canvas.getBoundingClientRect();
          const rect = findRect(rectsRef.current, event.clientX - bounds.left, event.clientY - bounds.top);
          if (rect && !rect.peer.is_selected) onSelectStock(rect.peer.asset_id);
        }}
      />
      {inspectorPeer ? (
        <div className="stock-market-context-inspector" aria-label="同业热力悬停信息">
          <strong>{inspectorPeer.name}</strong>
          <span>{inspectorPeer.symbol}</span>
          <span>{formatSignedPercent(inspectorPeer.change_pct)}</span>
          <span>{formatAmountYi(inspectorPeer.amount)}</span>
        </div>
      ) : null}
      <p className="muted" aria-label="同业样本说明">
        热力图与样本卡片仅展示成交额靠前的 {MAX_PEER_SAMPLE_SIZE} 只同业股票。
      </p>
      {selectedPeer && !selectedInSample ? (
        <p className="muted" aria-label="当前股票样本说明">
          当前股票未进入成交额前 {MAX_PEER_SAMPLE_SIZE}，热力图按同业成交额前 {MAX_PEER_SAMPLE_SIZE} 展示。
        </p>
      ) : null}
      <div className="stock-market-context-peer-list" aria-label="同业股票样本">
        {samplePeers.map((peer) => (
          <button
            key={peer.asset_id}
            type="button"
            aria-label={`打开同业 ${peer.name}`}
            className={peer.is_selected ? 'active' : undefined}
            onClick={() => {
              if (!peer.is_selected) onSelectStock(peer.asset_id);
            }}
          >
            <strong className="stock-market-context-peer-identity">{peer.name}</strong>
            <span className="stock-market-context-peer-code">代码 {peer.symbol}</span>
            <span className="stock-market-context-peer-change">涨跌幅 {formatSignedPercent(peer.change_pct)}</span>
            <small className="stock-market-context-peer-amount">成交额 {formatAmountYi(peer.amount)}</small>
          </button>
        ))}
      </div>
    </section>
  );
}
