export type TechBottleneckReviewFilters = {
  q: string;
  industry: string;
  concept_tag: string;
  evidence_strength: string;
  quality_reassessment_tier: string;
  concept_pollution_risk: string;
  route_around_or_substitution_risk: string;
  value_capture_risk: string;
  review_status: string;
  reviewer_decision: string;
};

export type TechBottleneckReadableFilterOptions = {
  industry: string[];
  concept_tag: string[];
  evidence_strength: string[];
  quality_reassessment_tier: string[];
  concept_pollution_risk: string[];
  route_around_or_substitution_risk: string[];
  value_capture_risk: string[];
  review_status: string[];
  reviewer_decision: string[];
};

type Props = {
  filters: TechBottleneckReviewFilters;
  options: TechBottleneckReadableFilterOptions;
  onChange: (next: TechBottleneckReviewFilters) => void;
};

const SELECT_FIELDS: Array<{
  key: keyof Omit<TechBottleneckReviewFilters, 'q'>;
  label: string;
}> = [
  { key: 'industry', label: '行业' },
  { key: 'concept_tag', label: '概念板块' },
  { key: 'evidence_strength', label: '证据强度' },
  { key: 'quality_reassessment_tier', label: '质量评级' },
  { key: 'concept_pollution_risk', label: '污染风险' },
  { key: 'route_around_or_substitution_risk', label: '替代风险' },
  { key: 'value_capture_risk', label: '价值捕获风险' },
  { key: 'review_status', label: '复盘状态' },
  { key: 'reviewer_decision', label: '人工结论' }
];

const OPTION_LABELS: Record<string, string> = {
  adjacent: '相邻观察',
  adjacent_watchlist: '相邻观察池',
  advanced_material: '先进材料',
  aerospace_defense_component: '航空航天/军工部件',
  beneficiary: '下游受益方',
  bottleneck: '瓶颈环节',
  canonical_90_internal_manual_review: '90池内部人工复核',
  chokepoint: '关键卡点',
  component: '关键部件',
  concept_only: '概念映射风险',
  core: '核心瓶颈',
  core_approval_candidate: '核心审批候选',
  core_pending: '核心待证据确认',
  contradictory: '存在反证',
  data_gap_core_equivalent_quality_pool: '数据缺口补证后等价质量层',
  downgrade_manual_review_required: '降级需人工复核',
  downgrade: '降级',
  doubler_data_gap_primary_source_backfilled: '翻倍股数据缺口补证',
  energy_storage_key_component: '储能关键部件',
  evidence_backfill_required: '需要证据补全',
  evidence_required: '需要证据确认',
  Excluded: '已排除',
  expansion_core_equivalent_quality_pool: '扩展等价质量层',
  expansion_2025_doubler_discovered: '2025翻倍股扩展发现',
  false_negative_rescue_core_equivalent_quality_pool: '误杀救回等价质量层',
  false_negative_rescue_backfilled: '误杀救回补证',
  high_end_equipment: '高端装备',
  high_precision_component: '高精密部件',
  hold: '暂缓',
  hold_for_review: '暂缓复核',
  industrial_software_or_simulation: '工业软件/仿真',
  insufficient: '证据不足',
  insufficient_existing_artifacts: '既有材料不足',
  internal_quality_pool: '内部质量层',
  keep: '保留',
  latent_core_equivalent_quality_pool: '潜在等价质量层',
  latent_manual_review: '潜在人工复核',
  latent_manual_review_batch1_core_equivalent_proposal: '潜在人工复核第一批等价提案',
  latent_manual_review_standard_core_equivalent_proposal: '潜在人工复核标准批等价提案',
  latent_standard: '潜在标准补证',
  latent_standard_core_equivalent_quality_pool: '潜在标准等价质量层',
  latent_standard_primary_source_backfilled: '潜在标准一手补证',
  likely_hard_tech_pending_evidence: '疑似硬科技待证据',
  likely_core_pending: '可能核心待证据',
  low: '低风险',
  manual_anchor_core_pending_evidence: '人工锚定核心待证据',
  missing_announcement: '缺公告证据',
  missing_annual_report: '缺年报',
  missing_architecture_shift: '缺架构变化证据',
  missing_financial_trace: '缺财务链路',
  missing_named_customer: '缺具名客户证据',
  missing_route_around: '缺替代路径证据',
  missing: '缺失',
  moderate: '中等',
  need_more_evidence: '需要更多证据',
  needs_manual_review: '需要人工复核',
  non_seed_tier_a_manual_review_adjacent: '非种子 Tier A 人工复核相邻',
  non_seed_tier_a_manual_review_core: '非种子 Tier A 人工复核核心',
  non_seed_tier_a_manual_review_downgrade: '非种子 Tier A 人工复核降级',
  non_seed_tier_a_manual_review_evidence: '非种子 Tier A 人工复核证据',
  not_detected_in_chunk: '片段未发现污染',
  not_detected_in_existing_artifacts: '既有材料未发现污染',
  not_relevant: '不相关',
  not_reviewed: '未复盘',
  nuclear_power: '核电',
  nuclear_valve_equipment: '核电阀门装备',
  pending: '待复盘',
  pending_manual_approval: '待人工审批',
  pending_primary_source: '待一手来源',
  pending_review: '待复盘',
  reject: '剔除',
  power_electronics_or_grid_equipment: '电力电子/电网装备',
  precision_component: '精密部件',
  primary_source_backfilled: '一手资料补证',
  risk_or_counter_evidence_present: '存在风险或反证',
  robotics_or_motion_control: '机器人/运动控制',
  seed_pollution_or_reject: '种子污染/拒绝',
  seed_tier_a: '种子 Tier A',
  seed_tier_b_reconciliation_adjacent: '种子 Tier B 校准相邻',
  seed_tier_b_reconciliation_evidence: '种子 Tier B 校准证据',
  seed_tier_b_reconciliation_reject: '种子 Tier B 校准拒绝',
  semiconductor_equipment_or_material: '半导体设备/材料',
  smart_grid: '智能电网',
  strong: '强',
  sufficient: '充分',
  supported: '有支撑',
  tier_1_core_review_priority: '一级：核心复盘优先',
  tier_2_strong_review_candidate: '二级：强复盘候选',
  tier_3_quality_or_value_capture_gap: '三级：质量/价值捕获缺口',
  tier_4_downgrade_or_reject_review: '四级：降级/剔除复核',
  'Tier A': 'Tier A 原层级',
  'Tier B': 'Tier B 原层级',
  uncertain: '不确定',
  unclear: '不清晰',
  verified_rescue_extension_proposal: '已验证救回扩展提案',
  verified_rescue_not_proposed: '已验证救回但未提案',
  v5_hydrated: 'v5 证据已水合',
  v5_targeted_hydrated: 'v5 定向补证已水合',
  v5_targeted: 'v5 定向补证',
  v7_proposal_new: 'v7 新增提案',
  quality_pool_v5: '质量层 v5',
  weak: '弱'
};

export function readableTechBottleneckOptionLabel(value: string): string {
  if (!value) return '全部';
  if (value.includes('|')) {
    return value
      .split('|')
      .map((part) => readableTechBottleneckOptionLabel(part.trim()))
      .join(' / ');
  }
  return OPTION_LABELS[value] ?? value;
}

export const EMPTY_TECH_BOTTLENECK_REVIEW_FILTERS: TechBottleneckReviewFilters = {
  q: '',
  industry: '',
  concept_tag: '',
  evidence_strength: '',
  quality_reassessment_tier: '',
  concept_pollution_risk: '',
  route_around_or_substitution_risk: '',
  value_capture_risk: '',
  review_status: '',
  reviewer_decision: ''
};

export function TechBottleneckFilterBar({ filters, options, onChange }: Props) {
  return (
    <section className="tech-bottleneck-filter-toolbar" aria-label="科技卡脖子复盘筛选">
      <label>
        股票代码/名称搜索
        <input value={filters.q} onChange={(event) => onChange({ ...filters, q: event.target.value })} />
      </label>
      {SELECT_FIELDS.map(({ key, label }) => (
        <label key={key}>
          {label}
          <select value={filters[key]} onChange={(event) => onChange({ ...filters, [key]: event.target.value })}>
            <option value="">全部</option>
            {(options[key] ?? []).map((value) => (
              <option key={value} value={value}>
                {readableTechBottleneckOptionLabel(value) || '空'}
              </option>
            ))}
          </select>
        </label>
      ))}
      <button type="button" onClick={() => onChange(EMPTY_TECH_BOTTLENECK_REVIEW_FILTERS)}>
        清空
      </button>
    </section>
  );
}
