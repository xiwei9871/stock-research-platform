export type OfficialStrategyFixture = {
  strategyId: 'lhb_shortline' | 'mid_trend' | 'tech_bottleneck';
  contractId: string;
  publishId: string;
  artifactVersion: string;
  performanceDate: string;
  totalReturn: number;
};

export const officialStrategies = {
  lhb_shortline: {
    strategyId: 'lhb_shortline',
    contractId: 'lhb_shortline:balanced:auction_enhanced_rerank:balanced',
    publishId: 'lhb-shortline-20260719',
    artifactVersion: 'lhb_publication_v1',
    performanceDate: '2026-07-19',
    totalReturn: 52.4
  },
  mid_trend: {
    strategyId: 'mid_trend',
    contractId: 'mid_trend:balanced:top5_weekly_max2_selective_trend_holding_protection_v1',
    publishId: 'mid-trend-20260718',
    artifactVersion: 'mid_trend_publication_v2',
    performanceDate: '2026-07-18',
    totalReturn: 49.12
  },
  tech_bottleneck: {
    strategyId: 'tech_bottleneck',
    contractId:
      'tech_bottleneck:balanced:strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d',
    publishId: 'tech-bottleneck-20260717',
    artifactVersion: 'tech_bottleneck_publication_v3',
    performanceDate: '2026-07-17',
    totalReturn: 70.5
  }
} as const satisfies Record<string, OfficialStrategyFixture>;
