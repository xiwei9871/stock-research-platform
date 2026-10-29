import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';
import { fetchMarketRegimeState, type RegimeStatePayload } from '../../api/client';

const MARKET_LABELS: Record<string, string> = {
  alla: 'A股整体', sse: '上证指数', szse: '深证成指', cyb: '创业板指',
};
const REGIME_LABELS: Record<string, string> = {
  NORMAL_RANGE: '正常区间', MILD_DRAWDOWN: '温和回撤',
  DECLINE: '下跌阶段', DEEP_DECLINE: '深度回撤', DATA_MISSING: '数据缺失',
};
const GROUP_LABELS: Record<string, string> = {
  g1: '全股票ETF', g2: '沪深300头部ETF', g3: '其他宽基ETF',
};

function useEChart() {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.EChartsType | null>(null);
  const roRef = useRef<ResizeObserver | null>(null);
  const [option, setOption] = useState<echarts.EChartsOption | null>(null);
  // chart lifecycle: create/update/dispose only inside effects, never during
  // render. The ResizeObserver is attached lazily — only once a chart
  // actually exists — so a mounted-but-empty panel creates no observer.
  useEffect(() => {
    const node = ref.current;
    if (!node || !option) return;
    const chart = chartRef.current ?? echarts.init(node);
    chartRef.current = chart;
    chart.setOption(option, { notMerge: true });
    if (!roRef.current && typeof ResizeObserver !== 'undefined') {
      roRef.current = new ResizeObserver(() => chart.resize());
      roRef.current.observe(node);
    }
  }, [option]);
  useEffect(() => {
    const onResize = () => chartRef.current?.resize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  useEffect(() => () => {
    roRef.current?.disconnect();
    roRef.current = null;
    chartRef.current?.dispose();
    chartRef.current = null;
  }, []);
  return { ref, setOption };
}

function pct(v?: number | null, digits = 1): string {
  if (v === null || v === undefined) return '—';
  return `${(v * 100).toFixed(digits)}%`;
}
function num(v?: number | null, digits = 1): string {
  if (v === null || v === undefined) return '—';
  return v.toFixed(digits);
}

export function MarketRegimeSection({ tradeDate }: { tradeDate: string }) {
  const [payload, setPayload] = useState<RegimeStatePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [market, setMarket] = useState('alla');
  const [group, setGroup] = useState('g1');
  const [refresh, setRefresh] = useState(0);
  const cont = useEChart();
  const etf = useEChart();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Clear previous payload immediately: stale metrics must never be shown
    // under a newly selected date/market while the request is in flight.
    setPayload(null);
    cont.setOption(null);
    etf.setOption(null);
    void fetchMarketRegimeState({ tradeDate, market, historyDays: 250 })
      .then((p) => { if (!cancelled) setPayload(p); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tradeDate, market, refresh]);

  const rows = payload?.modules.history.rows ?? [];
  useEffect(() => {
    if (!rows.length) {
      cont.setOption(null);
      return;
    }
    const dates = rows.map((r) => String(r.date));
    cont.setOption({
      grid: [{ left: 50, right: 50, top: 30, height: '32%' },
             { left: 50, right: 50, top: '48%', height: '38%' }],
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, show: false },
        { type: 'category', data: dates, gridIndex: 1 },
      ],
      yAxis: [
        { type: 'value', gridIndex: 0, name: 'dd120', axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
        { type: 'value', gridIndex: 1, name: '比率', min: 0 },
        { type: 'value', gridIndex: 1, name: 'pct', position: 'right', axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      ],
      tooltip: { trigger: 'axis' },
      series: [
        { name: '120日回撤', type: 'line', xAxisIndex: 0, yAxisIndex: 0,
          data: rows.map((r) => r[`${market}_dd120` as const] as number),
          color: '#c0392b', showSymbol: false },
        { name: '成交额5/20比', type: 'line', xAxisIndex: 1, yAxisIndex: 1,
          data: rows.map((r) => r.amt_ratio_5_20 as number),
          color: '#2980b9', showSymbol: false },
        { name: '60日均线上方占比', type: 'line', xAxisIndex: 1, yAxisIndex: 2,
          data: rows.map((r) => r.pct_ma60 as number),
          color: '#27ae60', showSymbol: false },
        { name: '广度20日变化', type: 'bar', xAxisIndex: 1, yAxisIndex: 2,
          data: rows.map((r) => r.pct_ma60_d20 as number),
          color: '#8e44ad' },
      ],
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, market]);

  const hist = payload?.modules.etf_flow.history[group] ?? [];
  useEffect(() => {
    if (!hist.length) {
      etf.setOption(null);
      return;
    }
    etf.setOption({
      grid: { left: 60, right: 60, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: hist.map((r) => r.date) },
      yAxis: [
        { type: 'value', name: '累计赎回/周期初AUM', axisLabel: { formatter: '{value}%' } },
      ],
      tooltip: { trigger: 'axis' },
      series: [
        { name: '累计净赎回占比', type: 'line', areaStyle: { opacity: 0.15 },
          data: hist.map((r) => r.cum_withdrawal_pct_aum0 ?? null),
          color: '#d35400', showSymbol: false },
      ],
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hist, group]);

  if (error) {
    return (
      <section className="market-regime-section">
        <h2>市场宏观状态</h2>
        <p className="muted">宏观状态数据暂不可用：{error}</p>
        <button type="button" onClick={() => setRefresh((v) => v + 1)}>
          重试
        </button>
      </section>
    );
  }

  const mods = payload?.modules;
  const regimeAll = mods?.regime.all_markets ?? {};
  const contM = mods?.continuity;
  const g = mods?.etf_flow.groups[group];

  return (
    <section className="market-regime-section">
      <h2>市场宏观状态（只读观察层）</h2>
      <p className="muted">
        数据截至 {payload?.trade_date ?? '—'} · ETF数据截至 {mods?.etf_flow.latest_etf_date ?? '—'}
        {mods?.etf_flow.status === 'STALE' ? '（ETF数据滞后于行情）' : ''}
        · 快照 {payload?.data_range?.snapshot_version ?? '—'}
        · 描述性状态，非预测。事前预警：{payload?.boundaries.advance_warning ?? '—'}
        {loading ? ' · 加载中…' : ''}
      </p>

      <div className="regime-cards">
        {Object.entries(MARKET_LABELS).map(([k, label]) => {
          const m = regimeAll[k];
          return (
            <button key={k} type="button"
              className={`regime-card ${market === k ? 'active' : ''} regime-${(m?.regime ?? '').toLowerCase()}`}
              onClick={() => setMarket(k)}>
              <span className="regime-card-title">{label}</span>
              <strong>{REGIME_LABELS[m?.regime ?? 'DATA_MISSING']}</strong>
              <span>dd120 {pct(m?.dd120)} · 已持续 {num(m?.regime_days, 0)} 交易日</span>
              <span>20日 {pct(m?.ret20)}</span>
            </button>
          );
        })}
      </div>
      <p className="muted small">
        阶段标签仅描述120日滚动回撤现状；「下跌阶段」不代表未来继续下跌，「温和回撤」不代表确认反转。
      </p>

      <h3>量能与广度持续性</h3>
      <div className="regime-kpis">
        <span>连低量 {num(contM?.lowvol_streak, 0)} 交易日</span>
        <span>20日低量占比 {pct(contM?.lowvol20_share)}</span>
        <span>成交额 5/20 {num(contM?.amount_ratio_5_20, 2)} · 20/60 {num(contM?.amount_ratio_20_60, 2)}</span>
        <span>60日均线上方 {pct(contM?.pct_above_ma60)}（20日 {pct(contM?.pct_ma60_d20)}）</span>
        <span>广度恶化连续 {num(contM?.breadth_bad_streak, 0)} 日</span>
        <span>McClellan {num(contM?.mcc_osc, 0)}</span>
      </div>
      <p className="muted small">{contM?.explanation}</p>
      <div className="regime-chart" ref={cont.ref} />
      {contM?.status === 'PARTIAL' ? (
        <p className="muted small">部分字段缺失：{(contM.missing_fields ?? []).join(', ')}</p>
      ) : null}

      <h3>ETF 资金配置</h3>
      <div className="regime-tabs" role="group" aria-label="ETF分组">
        {Object.entries(GROUP_LABELS).map(([k, label]) => (
          <button key={k} type="button" className={group === k ? 'active' : ''}
            onClick={() => setGroup(k)}>{label}</button>
        ))}
      </div>
      {g?.status === 'READY' ? (
        <>
          <div className="regime-kpis">
            <span>状态 {g.state} · 周期 {g.cycle_id}</span>
            <span>累计净申赎 {num(g.cum_flow)} 亿（负值=净赎回）</span>
            <span>占周期初AUM {num(g.cum_withdrawal_pct_aum0)}%
              （周期初 {num(g.cycle_start_aum, 0)} 亿 / 当前 {num(g.current_aum, 0)} 亿）</span>
            <span>确认撤持续 {num(g.ddur_days, 0)} 交易日</span>
            <span>20日速度 {num(g.vel20, 2)}%/日 · 近20日净申赎 {num(g.flow20)} 亿</span>
            <span>周期内最大撤离(至当日) {num(g.cycle_max_withdrawal_pct_to_date)}%</span>
          </div>
          <div className="regime-chart" ref={etf.ref} />
          <p className="muted small">
            {mods?.etf_flow.note}
            {g.inflow_diffusion === 'DATA_MISSING' || g.outflow_diffusion === 'DATA_MISSING'
              ? ' 资金入场/撤离扩散指标数据暂不可用。' : ''}
          </p>
        </>
      ) : (
        <p className="muted">该分组ETF资金数据暂不可用。</p>
      )}
    </section>
  );
}
