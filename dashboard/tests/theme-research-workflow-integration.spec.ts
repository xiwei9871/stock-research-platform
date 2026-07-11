import { expect, test, type Page } from '@playwright/test';

const themeContext = {
  asset_id: '002837.SZ',
  company_code: '002837.SZ',
  status: 'reviewed_context_available',
  driver_assessment: 'mixed_or_uncertain',
  theme_count: 1,
  mapping_count: 1,
  evidence_gap_count: 0,
  themes: [
    {
      theme_id: 'ai_power_value_capture_v1',
      theme_name: 'AI供电产业链',
      theme_type: 'ai_power',
      summary: 'AI power delivery chain',
          status: 'reviewed',
      dashboard_path: '/theme-research/ai_power_value_capture_v1',
      research_only: true,
      used_for_signal: false,
      used_for_admission: false
    }
  ],
  mappings: [
    {
      mapping_id: 'ai_power_liquid_cooling_002837_v1',
      theme_id: 'ai_power_value_capture_v1',
      company_code: '002837.SZ',
      company_name: '英维克',
      mapping_type: 'direct_product',
      confidence: 0.94,
      revenue_relevance: 'undisclosed',
      bottleneck_relevance: 'core',
      business_materiality: 'emerging_segment',
      business_stage: 'primary_business',
      product_or_service: '液冷系统',
      relationship_summary: '直接供应数据中心液冷产品。',
      review_status: 'reviewed',
      node: {
        node_id: 'liquid_cooling',
        theme_id: 'ai_power_value_capture_v1',
        parent_node_id: 'ai_server_integration',
        node_name: '液冷',
        node_type: 'subsystem',
        description: '高密度机柜液冷。',
        value_capture_score: 5,
        bottleneck_score: 4,
        localization_gap_score: 3,
        supply_tightness_score: 4,
        evidence_strength: 3,
        node_review_status: 'reviewed'
      },
      evidence_items: [
        {
          evidence_id: 'evidence-1',
          source_id: 'source-1',
          evidence_type: 'product_relationship',
          excerpt_locator: 'annual report p9',
          evidence_summary: '主营业务覆盖液冷产品。',
          related_company_codes: ['002837.SZ'],
          related_node_ids: ['liquid_cooling'],
          source: {
            source_id: 'source-1',
            source_type: 'company_filing',
            title: '2025年年度报告',
            publisher: '英维克',
            publish_date: '2026-03-30',
            url_or_ref: 'https://example.com/report',
            access_level: 'public',
            reliability_level: 'S0',
            review_status: 'accepted'
          }
        }
      ],
      reviewed_claims: [],
      company_relevance_score: 4.7,
      company_research_priority_score: 78.8,
      priority_band: 'high',
      recommended_action: 'deep_company_research',
      research_only: true,
      used_for_signal: false,
      used_for_admission: false
    }
  ],
  excluded_mappings: [],
  research_only: true,
  used_for_signal: false,
  used_for_admission: false,
  source: 'research.theme_research_company_mapping',
  warnings: []
};

async function mockWorkflowApi(page: Page) {
  const fixturePaths = [
    '/api/auth/me',
    '/api/platform/readiness',
    '/api/platform/summary',
    '/api/daily-review-lite',
    '/api/watchlists/default',
    '/api/assets/002837.SZ/profile',
    '/api/assets/002837.SZ/bars',
    '/api/assets/002837.SZ/news',
    '/api/assets/002837.SZ/research-reports',
    '/api/evidence-digest',
    '/api/stocks/002837.SZ/market-context/heatmap'
  ];
  await page.route('/api/**', (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (fixturePaths.some((path) => pathname === path)) return route.fallback();
    return route.fulfill({ json: { items: [], warnings: [] } });
  });
  await page.route('/api/auth/me', (route) =>
    route.fulfill({
      json: {
        user: {
          user_id: 'phase10-e2e',
          username: 'phase10_e2e',
          display_name: 'Phase 10 E2E',
          role: 'user',
          is_active: true
        }
      }
    })
  );
  await page.route('/api/platform/readiness**', (route) =>
    route.fulfill({ json: { display_trade_date: '2026-07-11', latest_market_date: '2026-07-11' } })
  );
  await page.route('/api/platform/summary**', (route) =>
    route.fulfill({ json: { latest_market_date: '2026-07-11' } })
  );
  await page.route('/api/daily-review-lite**', (route) =>
    route.fulfill({
      json: {
        trade_date: '2026-07-11',
        status: 'partial',
        run: { run_id: 'daily-1', source: 'report_run', report_type: 'daily_review_lite' },
        fallback: false,
        sections: [
          {
            key: 'theme_research',
            title: 'Theme Research',
            status: 'ready',
            items: [
              { label: '已审核主题', value: '1' },
              { label: '映射公司', value: '2' },
              { label: '近期审核更新', value: '1' },
              { label: '证据缺口', value: '15' },
              { label: '未完成证据轨道', value: 'humanoid_robotics_source_pack_v1' }
            ]
          }
        ],
        artifacts: [],
        theme_research: {
          trade_date: '2026-07-11',
          status: 'ready',
          reviewed_theme_count: 1,
          mapped_company_count: 2,
          reviewed_mapping_count: 2,
          recent_reviewed_update_count: 1,
          evidence_gap_count: 15,
          incomplete_evidence_tracks: ['humanoid_robotics_source_pack_v1'],
          mapped_companies: [
            {
              company_code: '002837.SZ',
              company_name: '英维克',
              theme_id: 'ai_power_value_capture_v1',
              theme_name: 'AI供电产业链',
              node_id: 'liquid_cooling',
              node_name: '液冷',
              company_research_priority_score: 78.8,
              stock_workspace_path: '/tech-bottleneck/stock/002837.SZ?source=theme_research',
              theme_dashboard_path: '/theme-research/ai_power_value_capture_v1'
            }
          ],
          recent_updates: [
            {
              update_id: 'review-1',
              theme_id: 'ai_power_value_capture_v1',
              object_type: 'claim',
              object_id: 'claim-1',
              from_status: 'draft',
              to_status: 'reviewed',
              decision: 'accept',
              summary: '完成公开证据复核',
              created_at: '2026-07-11T10:00:00+08:00'
            }
          ],
          research_only: true,
          used_for_signal: false,
          used_for_admission: false,
          source: 'research.theme_research_company_mapping',
          warnings: []
        },
        warnings: []
      }
    })
  );
  await page.route('/api/watchlists/default**', (route) =>
    route.fulfill({
      json: {
        watchlist_id: 'default',
        trade_date: '2026-07-11',
        items: [
          {
            watchlist_id: 'default',
            trade_date: '2026-07-11',
            asset_id: '002837.SZ',
            stock_code: '002837',
            stock_name: '英维克',
            priority: 8,
            signal_score: 82,
            primary_signal: 'observe',
            signal_tags: ['manual_review'],
            risk_tags: [],
            must_watch: true,
            reason_json: { reason: '人工观察', next_action: '继续验证' },
            theme_research_context: themeContext
          }
        ]
      }
    })
  );
  await page.route('/api/assets/002837.SZ/profile**', (route) =>
    route.fulfill({
      json: {
        asset_id: '002837.SZ',
        canonical_asset_id: '002837.SZ',
        asset: {
          asset_id: '002837.SZ',
          symbol: '002837',
          name: '英维克',
          exchange: 'SZ',
          board: 'main',
          is_active: true
        },
        bars: [
          {
            time: '2026-07-11',
            open: 40,
            high: 42,
            low: 39,
            close: 41,
            volume: 1000,
            amount: 41000
          }
        ],
        score: null,
        signals: [],
        decisions: [],
        outcomes: [],
        factor_values: [],
        coverage: {},
        theme_research_context: themeContext
      }
    })
  );
  await page.route('/api/assets/002837.SZ/bars**', (route) =>
    route.fulfill({ json: { asset_id: '002837.SZ', items: [] } })
  );
  await page.route('/api/assets/002837.SZ/news**', (route) =>
    route.fulfill({
      json: {
        asset_id: '002837.SZ',
        items: [],
        summary: {
          news_count_1d: 0,
          news_count_3d: 0,
          news_count_7d: 0,
          latest_published_at: null,
          source_count: 0,
          category_counts: []
        },
        warnings: []
      }
    })
  );
  await page.route('/api/assets/002837.SZ/research-reports**', (route) =>
    route.fulfill({
      json: {
        asset_id: '002837.SZ',
        summary: {
          report_count_30d: 0,
          report_count_90d: 0,
          broker_coverage_count_90d: 0,
          latest_report_date: null,
          latest_rating: '',
          latest_target_price: null
        },
        items: [],
        warnings: []
      }
    })
  );
  await page.route('/api/evidence-digest**', (route) => route.fulfill({ json: { warnings: [] } }));
  await page.route('/api/stocks/002837.SZ/market-context/heatmap**', (route) =>
    route.fulfill({
      json: {
        asset_id: '002837.SZ',
        trade_date: '2026-07-11',
        data_status: 'missing',
        selected: null,
        peers: [],
        warnings: []
      }
    })
  );
}

test('reviewed theme context flows through Daily Review, Watchlist and Stock Workspace', async ({ page }) => {
  await mockWorkflowApi(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/tech-bottleneck/stock/002837.SZ?source=theme_research');

  const workflowPayloads = await page.evaluate(async () => {
    const [dailyReview, watchlist] = await Promise.all([
      fetch('/api/daily-review-lite?trade_date=2026-07-11').then((response) => response.json()),
      fetch('/api/watchlists/default?trade_date=2026-07-11').then((response) => response.json())
    ]);
    return { dailyReview, watchlist };
  });

  expect(workflowPayloads.dailyReview.theme_research.mapped_company_count).toBe(2);
  expect(workflowPayloads.dailyReview.theme_research.used_for_signal).toBe(false);
  expect(workflowPayloads.watchlist.items[0].theme_research_context.company_code).toBe('002837.SZ');
  expect(workflowPayloads.watchlist.items[0].theme_research_context.used_for_admission).toBe(false);

  await expect(page.getByRole('heading', { name: '英维克 002837.SZ' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '主题研究' })).toBeVisible();
  await expect(page.getByText('价值量 5/5')).toBeVisible();
  await expect(page.getByText('卡脖子 4/5')).toBeVisible();
  await expect(page.getByText('仅用于研究，不参与评分、信号或准入')).toBeVisible();

  await page.screenshot({ path: 'test-results/theme-research-phase10-workflows.png', fullPage: true });
});
