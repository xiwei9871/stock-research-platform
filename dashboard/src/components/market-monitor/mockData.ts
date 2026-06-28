export type SectorType = 'industry' | 'concept';

export type MarketDataStatus = 'completed' | 'partial' | 'missing' | 'stale';

export type MarketOverviewIndex = {
  id: string;
  name: string;
  close: number | null;
  pctChange: number | null;
};

export type MarketOverview = {
  tradeDate: string;
  updatedAt: string;
  dataStatus: MarketDataStatus;
  totalAmount: number | null;
  upCount: number | null;
  downCount: number | null;
  limitUpCount: number | null;
  limitDownCount: number | null;
  indices: MarketOverviewIndex[];
};

export type SectorSnapshot = {
  sectorId: string;
  sectorName: string;
  sectorType: SectorType;
  pctChange: number;
  amount: number;
  upCount: number;
  downCount: number;
  mainNetInflow: number;
  netInflowRatio: number;
  leadingStockName: string | null;
};

export type SectorHeatmapItem = SectorSnapshot;

export type SectorFundFlowItem = SectorSnapshot;

export type LeadingStock = {
  assetId: string;
  name: string;
  symbol: string;
  pctChange: number;
  turnover: number;
  reason: string;
};

export type SectorDetail = SectorSnapshot & {
  summary: string;
  updatedAt: string;
  leadingStocks: LeadingStock[];
};

export type SectorFundFlowSet = {
  inflow: SectorFundFlowItem[];
  outflow: SectorFundFlowItem[];
};

export type MarketMonitorMockData = {
  marketOverview: MarketOverview;
  industryHeatmap: SectorHeatmapItem[];
  conceptHeatmap: SectorHeatmapItem[];
  sectorFundFlow: Record<SectorType, SectorFundFlowSet>;
  sectorDetails: Record<string, SectorDetail>;
};

export const mockMarketOverview: MarketOverview = {
  tradeDate: '2026-06-12',
  updatedAt: '2026-06-12 15:10',
  dataStatus: 'completed',
  totalAmount: 1526000000000,
  upCount: 3612,
  downCount: 1491,
  limitUpCount: 90,
  limitDownCount: 10,
  indices: [
    { id: 'shanghai', name: '上证指数', close: 3168.44, pctChange: 0.0087 },
    { id: 'shenzhen', name: '深证成指', close: 9821.31, pctChange: 0.0126 },
    { id: 'chinext', name: '创业板指', close: 1943.52, pctChange: 0.0189 },
    { id: 'star50', name: '科创50', close: 772.18, pctChange: 0.0213 },
    { id: 'beijing50', name: '北证50', close: 1088.67, pctChange: -0.0038 }
  ]
};

export const mockIndustryHeatmap: SectorHeatmapItem[] = [
  {
    sectorId: 'industry-semiconductor',
    sectorName: '半导体',
    sectorType: 'industry',
    pctChange: 0.0321,
    amount: 145800000000,
    upCount: 112,
    downCount: 18,
    mainNetInflow: 24800000000,
    netInflowRatio: 0.1701,
    leadingStockName: '北方华创'
  },
  {
    sectorId: 'industry-innovative-medicine',
    sectorName: '创新药',
    sectorType: 'industry',
    pctChange: 0.0158,
    amount: 82300000000,
    upCount: 61,
    downCount: 24,
    mainNetInflow: 10600000000,
    netInflowRatio: 0.1288,
    leadingStockName: '恒瑞医药'
  },
  {
    sectorId: 'industry-nonferrous',
    sectorName: '有色金属',
    sectorType: 'industry',
    pctChange: 0.0062,
    amount: 69400000000,
    upCount: 46,
    downCount: 29,
    mainNetInflow: 4200000000,
    netInflowRatio: 0.0605,
    leadingStockName: '紫金矿业'
  },
  {
    sectorId: 'industry-bank',
    sectorName: '银行',
    sectorType: 'industry',
    pctChange: -0.0034,
    amount: 59800000000,
    upCount: 9,
    downCount: 32,
    mainNetInflow: -2300000000,
    netInflowRatio: -0.0385,
    leadingStockName: '招商银行'
  },
  {
    sectorId: 'industry-coal',
    sectorName: '煤炭',
    sectorType: 'industry',
    pctChange: -0.0241,
    amount: 38400000000,
    upCount: 6,
    downCount: 29,
    mainNetInflow: -7800000000,
    netInflowRatio: -0.2031,
    leadingStockName: '中国神华'
  }
];

export const mockConceptHeatmap: SectorHeatmapItem[] = [
  {
    sectorId: 'concept-ai-compute',
    sectorName: 'AI算力',
    sectorType: 'concept',
    pctChange: 0.0432,
    amount: 198400000000,
    upCount: 128,
    downCount: 22,
    mainNetInflow: 32200000000,
    netInflowRatio: 0.1623,
    leadingStockName: '中际旭创'
  },
  {
    sectorId: 'concept-robotics',
    sectorName: '机器人',
    sectorType: 'concept',
    pctChange: 0.0218,
    amount: 91600000000,
    upCount: 74,
    downCount: 27,
    mainNetInflow: 12100000000,
    netInflowRatio: 0.1321,
    leadingStockName: '汇川技术'
  },
  {
    sectorId: 'concept-state-owned-reform',
    sectorName: '国企改革',
    sectorType: 'concept',
    pctChange: 0.0028,
    amount: 67200000000,
    upCount: 53,
    downCount: 41,
    mainNetInflow: 1800000000,
    netInflowRatio: 0.0268,
    leadingStockName: '中国中车'
  },
  {
    sectorId: 'concept-low-altitude',
    sectorName: '低空经济',
    sectorType: 'concept',
    pctChange: -0.0124,
    amount: 73400000000,
    upCount: 31,
    downCount: 66,
    mainNetInflow: -6800000000,
    netInflowRatio: -0.0926,
    leadingStockName: '万丰奥威'
  },
  {
    sectorId: 'concept-solid-state',
    sectorName: '固态电池',
    sectorType: 'concept',
    pctChange: -0.0076,
    amount: 45600000000,
    upCount: 22,
    downCount: 39,
    mainNetInflow: -3100000000,
    netInflowRatio: -0.068,
    leadingStockName: '德方纳米'
  }
];

export const mockSectorFundFlow: Record<SectorType, SectorFundFlowSet> = {
  industry: {
    inflow: [
      mockIndustryHeatmap[0],
      mockIndustryHeatmap[1],
      mockIndustryHeatmap[2]
    ],
    outflow: [
      mockIndustryHeatmap[4],
      mockIndustryHeatmap[3]
    ]
  },
  concept: {
    inflow: [
      mockConceptHeatmap[0],
      mockConceptHeatmap[1],
      mockConceptHeatmap[2]
    ],
    outflow: [
      mockConceptHeatmap[3],
      mockConceptHeatmap[4]
    ]
  }
};

const mockSectorDetails: Record<string, SectorDetail> = {
  'industry-semiconductor': {
    ...mockIndustryHeatmap[0],
    updatedAt: '2026-06-12 15:10',
    summary: '涨价链与先进制程设备共振，板块量价配合最好，资金净流入与涨幅匹配度高。',
    leadingStocks: [
      {
        assetId: 'CN:SZ:002371',
        name: '北方华创',
        symbol: '002371',
        pctChange: 0.0642,
        turnover: 13200000000,
        reason: '设备龙头领涨，机构净买入居前。'
      },
      {
        assetId: 'CN:SH:688981',
        name: '中芯国际',
        symbol: '688981',
        pctChange: 0.0415,
        turnover: 9800000000,
        reason: '大市值核心跟涨，成交额维持高位。'
      }
    ]
  },
  'industry-innovative-medicine': {
    ...mockIndustryHeatmap[1],
    updatedAt: '2026-06-12 15:10',
    summary: '医保谈判预期回暖带动估值修复，强度次于半导体，但资金承接稳定。',
    leadingStocks: [
      {
        assetId: 'CN:SH:600276',
        name: '恒瑞医药',
        symbol: '600276',
        pctChange: 0.0388,
        turnover: 8600000000,
        reason: '核心创新药权重放量走强。'
      }
    ]
  },
  'concept-ai-compute': {
    ...mockConceptHeatmap[0],
    updatedAt: '2026-06-12 15:10',
    summary: '算力链条从光模块扩散到服务器液冷，题材热度和资金强度双领先。',
    leadingStocks: [
      {
        assetId: 'CN:SZ:300308',
        name: '中际旭创',
        symbol: '300308',
        pctChange: 0.0711,
        turnover: 15600000000,
        reason: '光模块龙头加速，成为板块辨识度核心。'
      },
      {
        assetId: 'CN:SH:603019',
        name: '中科曙光',
        symbol: '603019',
        pctChange: 0.0456,
        turnover: 11200000000,
        reason: '服务器主线补涨，量能同步放大。'
      }
    ]
  }
};

export const mockSelectedSectorDetail = mockSectorDetails['industry-semiconductor'];

export function buildMarketMonitorMockData(tradeDate = mockMarketOverview.tradeDate): MarketMonitorMockData {
  const updatedAt = `${tradeDate} 15:10`;
  return {
    marketOverview: {
      ...mockMarketOverview,
      tradeDate,
      updatedAt
    },
    industryHeatmap: mockIndustryHeatmap.map((item) => ({ ...item })),
    conceptHeatmap: mockConceptHeatmap.map((item) => ({ ...item })),
    sectorFundFlow: {
      industry: {
        inflow: mockSectorFundFlow.industry.inflow.map((item) => ({ ...item })),
        outflow: mockSectorFundFlow.industry.outflow.map((item) => ({ ...item }))
      },
      concept: {
        inflow: mockSectorFundFlow.concept.inflow.map((item) => ({ ...item })),
        outflow: mockSectorFundFlow.concept.outflow.map((item) => ({ ...item }))
      }
    },
    sectorDetails: Object.fromEntries(
      Object.entries(mockSectorDetails).map(([sectorId, detail]) => [
        sectorId,
        {
          ...detail,
          tradeDate,
          updatedAt,
          leadingStocks: detail.leadingStocks.map((stock) => ({ ...stock }))
        } as SectorDetail
      ])
    )
  };
}
