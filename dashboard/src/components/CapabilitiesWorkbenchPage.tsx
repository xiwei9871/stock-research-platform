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

const STATE_LABELS: Record<string, string> = {
  supported: '支持', contested: '有争议', refuted: '已反驳',
  risk_flagged: '风险标记', unresolved: '未决',
};
const STATE_TONES: Record<string, string> = {
  supported: '#15803d', contested: '#b91c1c', refuted: '#7f1d1d',
  risk_flagged: '#c2410c', unresolved: '#6b7280',
};
const AREA_LABELS: Record<string, string> = {
  supply_constraint: '供给约束', non_substitutability: '技术不可替代性',
  entry_barrier: '进入壁垒',
};
const SUB_LABELS: Record<string, string> = {
  demand_growth: '需求增长', capacity_limited: '产能受限',
  effective_delivery_limited: '有效交付受限', supplier_count_limited: '供应商数量有限',
  cert_gated_supply: '认证门槛限供', functional_alternative_exists: '存在功能替代',
  performance_meets_requirement: '替代性能达标', switching_cost_cert: '切换认证成本',
  switching_time: '切换时间', alternative_commercialized: '替代已商业化',
  product_certification: '产品认证', customer_validation: '客户认证',
  mass_production_line_validation: '量产线验证', long_term_supply_qualification: '长期供应资格',
  yield_reliability: '良率可靠性',
};
const SCOPE_LABELS: Record<string, string> = {
  directly_comparable: '可直接比较', partially_comparable: '部分可比',
  not_comparable: '不可直接比较', insufficient_evidence: '证据不足',
};

function JudgmentBlock({ node }: { node: CapWorkbenchNode }) {
  const ta = node.technical_assessment;
  const hypos = node.hypothesis_assessment ?? [];
  const pairs = node.pairwise_scope ?? [];
  return (
    <div style={{ marginTop: 8, borderTop: '1px dashed #d1d5db', paddingTop: 8 }}>
      <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>研究判断</div>
      {ta ? (
        <div style={{ fontSize: 12, marginBottom: 6 }}>
          {Object.entries(ta).map(([area, v]) => (
            <div key={area} style={{ marginBottom: 3 }}>
              <span style={{ fontWeight: 600 }}>{AREA_LABELS[area] ?? area}</span>
              <code style={{ marginLeft: 6 }}>{v.assessment ?? '—'}</code>
              <span style={{ color: '#6b7280', marginLeft: 8 }}>
                {Object.entries(v.sub_checks ?? {}).map(([k, s]) =>
                  `${SUB_LABELS[k] ?? k}:${s}`).join(' · ')}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {pairs.length ? (
        <div style={{ fontSize: 12, marginBottom: 6 }}>
          <span style={{ fontWeight: 600 }}>可比口径：</span>
          {pairs.map((p, i) => (
            <span key={i} style={{ marginRight: 10, color: p.comparison_scope === 'directly_comparable' ? '#15803d' : '#92400e' }}>
              {p.a}×{p.b} {SCOPE_LABELS[p.comparison_scope] ?? p.comparison_scope}（{p.reason}）
            </span>
          ))}
        </div>
      ) : null}
      {hypos.map((h) => (
        <div key={h.hypothesis_id} style={{ fontSize: 12, margin: '4px 0 4px 8px',
          borderLeft: `3px solid ${STATE_TONES[h.assessment_state] ?? '#9ca3af'}`, paddingLeft: 8 }}>
          <div>
            <code>{h.hypothesis_id}</code>
            <span style={{ fontWeight: 600, color: STATE_TONES[h.assessment_state] ?? '#374151', marginLeft: 6 }}>
              {STATE_LABELS[h.assessment_state] ?? h.assessment_state}
            </span>
            <span style={{ color: '#6b7280' }}> · {h.claim_role} · 独立来源 {h.independent_source_count ?? 0}
              {typeof h.supporting_source_count === 'number'
                ? `（正${h.supporting_source_count}/反${h.counter_source_count ?? 0}）`
                : ''}
            </span>
          </div>
          {h.alternative_explanations?.length ? (
            <div style={{ color: '#0369a1' }}>替代解释：{h.alternative_explanations.join('；')}</div>
          ) : null}
          {h.decisive_gaps?.length ? (
            <div style={{ color: '#92400e' }}>决定性缺口：{h.decisive_gaps.join(', ')}</div>
          ) : null}
          {h.revision_triggers?.length ? (
            <div style={{ color: '#6b7280' }}>修订触发：{h.revision_triggers.join('；')}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function ThemeSummary({ ts }: { ts: NonNullable<CapWorkbenchIndex['theme_synthesis']> }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ border: '1px solid #c7d2fe', borderRadius: 8, padding: 10, marginBottom: 12, background: '#eef2ff' }}>
      <button onClick={() => setOpen(!open)} style={{ all: 'unset', cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
        主题研究摘要（研究用，非评级/建议） {open ? '收起' : '展开'}
      </button>
      {open ? (
        <div style={{ marginTop: 8, fontSize: 12 }}>
          <div style={{ fontWeight: 600 }}>已有研究发现</div>
          {ts.key_findings.map((f, i) => <div key={i} style={{ margin: '1px 0 1px 12px' }}>{f}</div>)}
          <div style={{ fontWeight: 600, marginTop: 6 }}>主要竞争假设</div>
          {ts.competing_hypotheses.map((h, i) => (
            <div key={i} style={{ margin: '1px 0 1px 12px' }}>
              <code>{h.hypothesis_id}</code>
              <span style={{ color: STATE_TONES[h.state] ?? '#374151', marginLeft: 6 }}>
                {STATE_LABELS[h.state] ?? h.state}
              </span>
              <span style={{ color: '#6b7280' }}> · {h.node_id} · 独立来源 {h.independent_source_count ?? '—'}</span>
            </div>
          ))}
          <div style={{ fontWeight: 600, marginTop: 6 }}>尚无法确认（{ts.core_unresolved.length}）</div>
          {ts.core_unresolved.slice(0, 10).map((u, i) => (
            <div key={i} style={{ margin: '1px 0 1px 12px', color: '#6b7280' }}>
              <code>{u.claim_id}</code> · {u.node_id} · {u.verdict}
            </div>
          ))}
          <div style={{ fontWeight: 600, marginTop: 6 }}>最有价值的下一项验证</div>
          {ts.next_verification.slice(0, 10).map((v, i) => (
            <div key={i} style={{ margin: '1px 0 1px 12px' }}>{v}</div>
          ))}
          <div style={{ color: '#6b7280', marginTop: 6 }}>
            覆盖：{ts.coverage?.nodes_with_cases ?? 0}/{ts.coverage?.theme_nodes ?? 0} 主题节点有案例
            {ts.coverage?.coverage_gap_nodes?.length ? ` · 缺口 ${ts.coverage.coverage_gap_nodes.length} 个` : ''}
            {ts.coverage?.read_source ? ` · 读源 ${ts.coverage.read_source}` : ''}
          </div>
        </div>
      ) : null}
    </div>
  );
}

const PRIORITY_TONES: Record<string, string> = {
  high: '#b91c1c', medium: '#92400e', low: '#6b7280',
};

function VerificationTasks({ tasks }: { tasks: NonNullable<CapWorkbenchIndex['verification_tasks']> }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={{ border: '1px solid #fde68a', borderRadius: 8, padding: 10, marginBottom: 12, background: '#fffbeb' }}>
      <button onClick={() => setOpen(!open)} style={{ all: 'unset', cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
        下一步验证任务（{tasks.length} · 只读建议，不自动执行） {open ? '收起' : '展开'}
      </button>
      {open ? (
        <div style={{ marginTop: 8, fontSize: 12 }}>
          {tasks.slice(0, 30).map((t) => (
            <div key={t.task_id} style={{ margin: '3px 0 3px 8px', borderLeft: `3px solid ${PRIORITY_TONES[t.priority] ?? '#9ca3af'}`, paddingLeft: 8 }}>
              <div>
                <code>{t.task_id}</code>
                <span style={{ fontWeight: 600, color: PRIORITY_TONES[t.priority] ?? '#374151', marginLeft: 6 }}>
                  [{t.priority}]
                </span>
                <span style={{ marginLeft: 6 }}>{t.question}</span>
              </div>
              <div style={{ color: '#6b7280' }}>
                {t.node_id}{t.company_code ? ` / ${t.company_code}` : ''} · owner {t.owner}
                {t.hypothesis_id ? ` · 假设 ${t.hypothesis_id}` : ''}
                {t.required_evidence?.length ? ` · 需证据 ${t.required_evidence.join(', ')}` : ''}
              </div>
              <div style={{ color: '#92400e' }}>优先级依据：{t.priority_reason} · 来源 {t.source_capabilities?.join('+')}</div>
            </div>
          ))}
          {tasks.length > 30 ? <div style={{ color: '#6b7280' }}>…共 {tasks.length} 条，其余略</div> : null}
        </div>
      ) : null}
    </div>
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
        {changes.materiality ? (
          <span style={{ color: '#92400e' }}>
            {' '}· material {changes.materiality.counts?.material ?? 0}
            {' '}· notable {changes.materiality.counts?.notable ?? 0}
            {changes.materiality.requires_re_review ? ' · 需人工复核' : ''}
          </span>
        ) : null}
      </div>
      {items.slice(0, 15).map((c, i) => (
        <div key={i} style={{ margin: '1px 0 1px 12px', color: '#374151' }}>
          <em>[{c.kind}]</em> <code>{c.field}</code>{' '}
          {String(c.from ?? '—')} → {String(c.to ?? '—')}
          {c.materiality ? (
            <span style={{ color: c.materiality === 'material' ? '#b91c1c' : '#6b7280' }}>
              {' '}· {c.materiality}{c.explanation ? `（${c.explanation}）` : ''}
            </span>
          ) : null}
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
                  {c.scope_class ? <span style={{ color: '#0369a1' }}> [{c.scope_class}]</span> : null}
                  <span style={{ color: '#6b7280' }}> · 认证 {c.cert ?? '—'} · 交付 {c.delivery ?? '—'} · 收入 {c.revenue ?? '—'} · 订单 {c.order ?? '—'}</span>
                  {c.confirmed_stages?.length ? (
                    <span style={{ color: '#15803d' }}> · 兑现 {c.confirmed_stages.length}/6 阶段</span>
                  ) : null}
                  {typeof c.evidence_coverage === 'number' ? (
                    <span style={{ color: '#9ca3af' }}> · 证据覆盖 {c.evidence_coverage}</span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          <JudgmentBlock node={node} />
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
          {index.theme_synthesis ? <ThemeSummary ts={index.theme_synthesis} /> : null}
          {index.verification_tasks?.length ? <VerificationTasks tasks={index.verification_tasks} /> : null}
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
