import { useEffect, useState } from 'react';

import {
  listCapabilityWorkbenches,
  loadCapabilityWorkbench,
  type CapBucketEntry,
  type CapWorkbenchIndex,
  type CapWorkbenchNode,
  type CapWorkbenchTheme
} from '../api/capabilities';

const BUCKETS: Array<{ key: keyof NonNullable<CapWorkbenchNode['synthesis']>; label: string; tone: string }> = [
  { key: 'favorable_support', label: '正向支持', tone: '#15803d' },
  { key: 'market_structure', label: '格局事实', tone: '#0369a1' },
  { key: 'counter_evidence', label: '反证', tone: '#b91c1c' },
  { key: 'hype_risks', label: '炒作风险', tone: '#c2410c' },
  { key: 'unresolved', label: '未决', tone: '#6b7280' }
];

function Bucket({ label, tone, entries }: { label: string; tone: string; entries: CapBucketEntry[] }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600, color: tone, fontSize: 13 }}>
        {label}（{entries.length}）
      </div>
      {entries.map((e) => (
        <div key={`${e.capability}:${e.claim_id}`} style={{ fontSize: 12, margin: '2px 0 2px 12px', color: '#374151' }}>
          <code>{e.claim_id}</code> <em>[{e.verdict}]</em> {e.hypothesis ?? ''}
          {e.source_ids?.length ? (
            <span style={{ color: '#6b7280' }}> · 来源 {e.source_ids.join(', ')}</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function CompanyLink({ code, link }: { code: string; link?: string }) {
  if (!link) return <code>{code}</code>;
  return (
    <a href={link} style={{ fontFamily: 'monospace' }}>{code}</a>
  );
}

function ChangesBlock({ changes }: { changes: NonNullable<CapWorkbenchNode['changes']> }) {
  if (!changes.baseline_found) {
    return <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>历史变化：无基线（首次研究建立基线）</div>;
  }
  const items = changes.items ?? [];
  return (
    <div style={{ fontSize: 12, marginTop: 6 }}>
      <div style={{ fontWeight: 600 }}>
        历史变化（vs 基线 v{changes.baseline_version}）：
        {changes.state_changed
          ? ` 新增 ${changes.added ?? 0} · 删除 ${changes.removed ?? 0} · 变更 ${changes.changed ?? 0}`
          : ' 无变化'}
      </div>
      {items.slice(0, 15).map((c, i) => (
        <div key={i} style={{ margin: '1px 0 1px 12px', color: '#374151' }}>
          <em>[{c.kind}]</em> <code>{c.field}</code>{' '}
          {String(c.from ?? '—')} → {String(c.to ?? '—')}
        </div>
      ))}
    </div>
  );
}

function NodeCard({ node }: { node: CapWorkbenchNode }) {
  const [open, setOpen] = useState(false);
  const noCase = node.status === 'no_case';
  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 10, marginBottom: 8,
                  background: noCase ? '#fafafa' : undefined }}>
      <button
        onClick={() => setOpen(!open)}
        style={{ all: 'unset', cursor: 'pointer', display: 'block', width: '100%' }}
      >
        <div style={{ display: 'flex', gap: 12, alignItems: 'baseline' }}>
          <strong>{node.node_id}</strong>
          {node.theme_node_id && node.theme_node_id !== node.node_id ? (
            <span style={{ color: '#6b7280', fontSize: 12 }}>归属主题节点 {node.theme_node_id}</span>
          ) : null}
          {node.theme_node ? (
            <span style={{ color: '#6b7280', fontSize: 12 }}>{node.theme_node}</span>
          ) : null}
          <span style={{ fontSize: 12 }}>
            {noCase
              ? <>覆盖缺口：<code>无研究案例（{node.coverage_owner}）</code></>
              : <>节点结论：<code>{node.node_verdict ?? node.status ?? '—'}</code></>}
          </span>
          <span style={{ marginLeft: 'auto', fontSize: 12, color: '#6b7280' }}>{open ? '收起' : '展开'}</span>
        </div>
        {node.cap_statuses ? (
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
            {Object.entries(node.cap_statuses).map(([c, s]) => `${c}:${s}`).join(' · ')}
          </div>
        ) : null}
      </button>
      {open && noCase ? (
        <div style={{ marginTop: 10, borderTop: '1px solid #f3f4f6', paddingTop: 8, fontSize: 12 }}>
          <div style={{ color: '#92400e' }}>
            该主题节点尚无研究案例 —— 覆盖缺口由 {node.coverage_owner} 负责，不视为数据缺失
            {node.node_review_status ? ` · 审核状态 ${node.node_review_status}` : ''}
          </div>
          {node.mapped_companies?.length ? (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>映射公司（按审核状态）</div>
              {node.mapped_companies.map((c) => (
                <div key={c.stock_code} style={{ margin: '2px 0 2px 12px' }}>
                  <CompanyLink code={c.stock_code} link={c.dashboard_link} />
                  <span style={{ color: '#6b7280' }}> · {c.review_status ?? 'unknown'}</span>
                </div>
              ))}
            </div>
          ) : null}
          {node.theme_link ? (
            <div style={{ marginTop: 6 }}>
              <a href={node.theme_link} style={{ fontSize: 12 }}>在主题研究中查看 →</a>
            </div>
          ) : null}
        </div>
      ) : null}
      {open && !noCase && node.synthesis ? (
        <div style={{ marginTop: 10, borderTop: '1px solid #f3f4f6', paddingTop: 8 }}>
          {BUCKETS.map((b) => (
            <Bucket key={b.key} label={b.label} tone={b.tone} entries={node.synthesis?.[b.key] ?? []} />
          ))}
          {node.companies?.length ? (
            <div style={{ fontSize: 12, marginTop: 6 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>公司</div>
              {node.companies.map((c) => (
                <div key={c.stock_code} style={{ margin: '2px 0 2px 12px' }}>
                  <CompanyLink code={c.stock_code} link={c.dashboard_link} /> {c.overall_verdict ?? 'no_dossier'}
                  <span style={{ color: '#6b7280' }}> · 交付 {c.delivery ?? '—'} · 收入 {c.revenue ?? '—'} · 订单 {c.order ?? '—'}</span>
                </div>
              ))}
            </div>
          ) : null}
          {node.changes ? <ChangesBlock changes={node.changes} /> : null}
          {node.evidence_refs?.length ? (
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 6 }}>
              证据引用 {node.evidence_refs.length} 条（{node.evidence_refs.slice(0, 8).join(', ')}{node.evidence_refs.length > 8 ? '…' : ''}）
              · 上游指纹 {node.upstream_fingerprints?.length ?? 0} 条
            </div>
          ) : null}
        </div>
      ) : null}
      {open && node.error ? <div style={{ color: '#b91c1c', fontSize: 12 }}>错误：{node.error}</div> : null}
    </div>
  );
}

export function CapabilitiesWorkbenchPage() {
  const [themes, setThemes] = useState<CapWorkbenchTheme[]>([]);
  const [selected, setSelected] = useState('');
  const [index, setIndex] = useState<CapWorkbenchIndex | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    listCapabilityWorkbenches()
      .then((r) => {
        setThemes(r.themes);
        if (r.themes.length) setSelected((cur) => cur || r.themes[0].theme_id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    loadCapabilityWorkbench(selected)
      .then(setIndex)
      .catch((e) => { setIndex(null); setError(String(e)); });
  }, [selected]);

  return (
    <div style={{ padding: 16, maxWidth: 1100 }}>
      <h2 style={{ margin: '0 0 8px' }}>能力研究工作台</h2>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        只读浏览 · research_only · 主题 → 节点 → 公司 → 综合结论 → 证据 → 缺口
      </div>
      {error ? <div style={{ color: '#b91c1c', marginBottom: 8 }}>{error}</div> : null}
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 13, marginRight: 8 }}>主题</label>
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {themes.map((t) => (
            <option key={t.theme_id} value={t.theme_id}>
              {t.theme_id}（{t.node_count} 节点 / {t.gap_count} 缺口）
            </option>
          ))}
        </select>
        {index ? (
          <span style={{ fontSize: 12, color: '#6b7280', marginLeft: 12 }}>
            as_of {index.as_of} · run {index.run_id}
            {index.read_source ? ` · 来源 ${index.read_source}` : ''}
            {typeof index.theme_node_count === 'number'
              ? ` · 主题节点 ${index.covered_node_count}/${index.theme_node_count} 有案例`
              : ''}
            {index.theme_link ? (
              <> · <a href={index.theme_link}>主题研究 →</a></>
            ) : null}
          </span>
        ) : null}
        {index?.pit_note ? (
          <div style={{ fontSize: 11, color: '#92400e', marginTop: 4 }}>时点说明：{index.pit_note}</div>
        ) : null}
      </div>
      {index ? (
        <>
          {(index.nodes ?? []).map((n) => <NodeCard key={n.node_id} node={n} />)}
          <div style={{ marginTop: 12, borderTop: '1px solid #e5e7eb', paddingTop: 8 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
              DATA/CAP 缺口（{index.gap_backlog.length} 条，已去重）
            </div>
            {(index.gap_backlog ?? []).slice(0, 50).map((g, i) => (
              <div key={i} style={{ fontSize: 12, color: '#374151' }}>
                <code>{g.owner}:{g.kind}</code> {g.item}
                <span style={{ color: '#9ca3af' }}> · {g.source_capabilities?.join('+')}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
