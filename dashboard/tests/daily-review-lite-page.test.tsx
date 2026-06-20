import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DailyReviewLiteResponse } from '../src/api/types';
import { DailyReviewLitePage } from '../src/pages/DailyReviewLitePage';

const apiMocks = vi.hoisted(() => ({
  fetchDailyReviewLite: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function makeResponse(overrides: Partial<DailyReviewLiteResponse> = {}): DailyReviewLiteResponse {
  return {
    trade_date: '2026-06-20',
    state: 'ready',
    selected_run: {
      run_id: 'daily_review_v1:2026-06-20:abc123',
      report_type: 'daily_review_v1',
      status: 'success',
      updated_at: '2026-06-20T22:00:00Z',
      source: 'report_run',
      artifact_health: 'healthy',
      artifact_health_detail: {
        daily_review_json: 'healthy'
      }
    },
    summary: {
      market_status: 'neutral',
      overall_position_bias: 'balanced',
      lhb_conclusion: 'observe',
      mid_trend_conclusion: 'hold',
      technical_bottleneck_conclusion: 'watch',
      must_review_asset_ids: [],
      warning_count: 0
    },
    warnings: [],
    missing_sources: [],
    sections: {
      data_readiness: {
        status: 'success',
        warnings: [],
        sources: {}
      },
      market_review: {
        status: 'success',
        warnings: [],
        payload: {}
      },
      strategy_summaries: {
        lhb: {
          strategy_id: 'lhb',
          status: 'success',
          warnings: [],
          summary: {},
          top_items: []
        },
        mid_trend: {
          strategy_id: 'mid_trend',
          status: 'success',
          warnings: [],
          summary: {},
          top_items: []
        },
        technical_bottleneck: {
          strategy_id: 'technical_bottleneck',
          status: 'success',
          warnings: [],
          summary: {},
          top_items: []
        }
      },
      holding_review: {
        status: 'empty',
        warnings: [],
        items: []
      },
      operator_plan: {
        status: 'success',
        warnings: [],
        payload: {}
      },
      next_day_checklist: {
        status: 'success',
        warnings: [],
        must_review_items: [],
        forbidden_actions: [],
        data_warnings: []
      }
    },
    artifacts: [],
    ...overrides
  };
}

function renderResolvedPage(response: DailyReviewLiteResponse | null, initialTradeDate?: string) {
  apiMocks.fetchDailyReviewLite.mockResolvedValueOnce(response);
  render(<DailyReviewLitePage initialTradeDate={initialTradeDate} />);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DailyReviewLitePage', () => {
  it('renders the ready-state shell after loading the default trade date', async () => {
    const request = createDeferred<DailyReviewLiteResponse>();
    apiMocks.fetchDailyReviewLite.mockReturnValueOnce(request.promise);

    render(<DailyReviewLitePage />);

    expect(screen.getByText('Loading Daily Review Lite...')).toBeInTheDocument();
    expect(apiMocks.fetchDailyReviewLite).toHaveBeenCalledWith('2026-06-20', undefined);

    request.resolve(makeResponse());

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Daily Review Lite' })).toBeInTheDocument();
    });

    expect(
      screen.getByText('Structured read-only review of the Daily Review v1 report package')
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Trade Date')).toHaveValue('2026-06-20');
    expect(screen.getByText('Loaded from report.run')).toBeInTheDocument();
    expect(screen.getByText('daily_review_v1:2026-06-20:abc123')).toBeInTheDocument();
  });

  it('renders an error state when the fetch rejects', async () => {
    apiMocks.fetchDailyReviewLite.mockRejectedValueOnce(new Error('network offline'));

    render(<DailyReviewLitePage />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load Daily Review Lite: network offline')).toBeInTheDocument();
    });
  });

  it('renders a null payload fallback when no data is returned', async () => {
    renderResolvedPage(null);

    await waitFor(() => {
      expect(screen.getByText('No data returned.')).toBeInTheDocument();
    });
  });

  it('renders the empty-state shell with the selected trade date preserved', async () => {
    renderResolvedPage(
      makeResponse({
        trade_date: '2026-06-21',
        state: 'empty',
        selected_run: {
          ...makeResponse().selected_run!,
          run_id: 'daily_review_v1:2026-06-21:def456'
        }
      }),
      '2026-06-21'
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Daily Review Lite' })).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Trade Date')).toHaveValue('2026-06-21');
    expect(screen.getByText('No report found for selected date')).toBeInTheDocument();
    expect(screen.getByText('daily_review_v1:2026-06-21:def456')).toBeInTheDocument();
  });

  it('renders the failed-state shell while keeping banner metadata and safe artifacts visible', async () => {
    renderResolvedPage(
      makeResponse({
        trade_date: '2026-06-22',
        state: 'failed',
        selected_run: {
          ...makeResponse().selected_run!,
          run_id: 'daily_review_v1:2026-06-22:ghi789',
          artifact_health: 'invalid'
        },
        artifacts: [
          {
            key: 'daily_review_json',
            label: 'Daily Review JSON',
            kind: 'json',
            required: true,
            available: true,
            filename: 'daily_review_2026-06-22.json',
            content_type: 'application/json',
            url: '/api/daily-review-lite/artifacts?trade_date=2026-06-22&key=daily_review_json'
          }
        ]
      }),
      '2026-06-22'
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Daily Review Lite' })).toBeInTheDocument();
    });

    expect(screen.getByText('Package artifacts could not be read or parsed.')).toBeInTheDocument();
    expect(screen.getByText('daily_review_v1:2026-06-22:ghi789')).toBeInTheDocument();
    expect(screen.getByText('Artifact health: invalid')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Daily Review JSON' })).toHaveAttribute(
      'href',
      '/api/daily-review-lite/artifacts?trade_date=2026-06-22&key=daily_review_json'
    );
  });

  it('renders the fallback source label when the selected run came from fallback scanning', async () => {
    renderResolvedPage(
      makeResponse({
        selected_run: {
          ...makeResponse().selected_run!,
          source: 'fallback'
        }
      })
    );

    await waitFor(() => {
      expect(screen.getByText('Loaded from fallback package scan')).toBeInTheDocument();
    });
  });

  it('renders warnings and missing sources in a structured banner without duplicate key warnings', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderResolvedPage(
      makeResponse({
        warnings: ['source_missing:lhb_feed', 'source_missing:lhb_feed'],
        missing_sources: [
          {
            source_key: 'raw_lhb_payload',
            summary: 'LHB payload missing for trade date.',
            affected_sections: ['lhb', 'next_day_checklist'],
            confidence_impact: 'LHB confidence reduced'
          },
          {
            source_key: null,
            summary: 'Operator notes package missing.',
            affected_sections: [],
            confidence_impact: null
          }
        ]
      })
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Daily Review Lite' })).toBeInTheDocument();
    });

    const warnings = within(screen.getByRole('list', { name: 'Warnings' })).getAllByRole('listitem');
    expect(warnings).toHaveLength(2);
    expect(warnings[0]).toHaveTextContent('source_missing:lhb_feed');
    expect(warnings[1]).toHaveTextContent('source_missing:lhb_feed');

    const missingSources = within(screen.getByRole('list', { name: 'Missing sources' })).getAllByRole(
      'listitem'
    );
    expect(missingSources[0]).toHaveTextContent('raw_lhb_payload');
    expect(missingSources[0]).toHaveTextContent('LHB payload missing for trade date.');
    expect(missingSources[0]).toHaveTextContent('Affected sections: lhb, next_day_checklist');
    expect(missingSources[0]).toHaveTextContent('Confidence impact: LHB confidence reduced');
    expect(missingSources[1]).toHaveTextContent('Operator notes package missing.');
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it('renders the fixed section stack, strategy cards, checklist details, artifacts, and local warnings for a partial payload', async () => {
    renderResolvedPage(
      makeResponse({
        state: 'partial',
        selected_run: {
          ...makeResponse().selected_run!,
          source: 'fallback',
          status: 'partial'
        },
        sections: {
          data_readiness: {
            status: 'partial',
            warnings: ['raw_lhb_payload missing'],
            sources: {
              raw_lhb_payload: {
                available: false
              }
            }
          },
          market_review: {
            status: 'success',
            warnings: [],
            payload: {
              breadth: 'mixed'
            }
          },
          strategy_summaries: {
            lhb: {
              strategy_id: 'lhb',
              status: 'partial',
              warnings: ['LHB feed incomplete'],
              summary: {
                conclusion: 'observe'
              },
              top_items: []
            },
            mid_trend: {
              strategy_id: 'mid_trend',
              status: 'success',
              warnings: [],
              summary: {
                conclusion: 'hold'
              },
              top_items: []
            },
            technical_bottleneck: {
              strategy_id: 'technical_bottleneck',
              status: 'success',
              warnings: [],
              summary: {
                conclusion: 'watch'
              },
              top_items: []
            }
          },
          holding_review: {
            status: 'empty',
            warnings: ['no active holdings snapshot'],
            items: []
          },
          operator_plan: {
            status: 'success',
            warnings: [],
            payload: {
              notes: ['reduce turnover']
            }
          },
          next_day_checklist: {
            status: 'partial',
            warnings: ['one checklist source delayed'],
            must_review_items: [
              {
                asset_id: '600000.SH',
                ts_code: '600000.SH',
                stock_name: '浦发银行',
                strategy_ids: ['mid_trend'],
                reasons: [
                  {
                    strategy_id: 'mid_trend',
                    summary: 'Earnings gap needs confirmation',
                    detail: 'watch for volume follow-through'
                  }
                ],
                actions: ['Review opening auction', 'Confirm breakout holds'],
                review_priority: 'high'
              }
            ],
            forbidden_actions: ['Do not add new positions without confirmation'],
            data_warnings: ['operator notes pending']
          }
        },
        artifacts: [
          {
            key: 'daily_review_json',
            label: 'Daily Review JSON',
            kind: 'json',
            required: true,
            available: true,
            filename: 'daily_review_2026-06-20.json',
            content_type: 'application/json',
            url: '/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=daily_review_json'
          }
        ]
      })
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Daily Review Lite' })).toBeInTheDocument();
    });

    expect(screen.getByText('Loaded from fallback package scan')).toBeInTheDocument();

    const headings = screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent);
    expect(headings).toEqual([
      'Data Readiness',
      'Market Review',
      'Strategy Summaries',
      'Holding Review',
      'Operator Plan',
      'Next-day Checklist',
      'Artifacts'
    ]);

    expect(screen.getByRole('heading', { name: 'LHB' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Mid Trend' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Technical Bottleneck' })).toBeInTheDocument();
    expect(screen.getByText('浦发银行')).toBeInTheDocument();
    expect(screen.getByText('watch for volume follow-through')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Daily Review JSON' })).toHaveAttribute(
      'href',
      '/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=daily_review_json'
    );
    expect(screen.getByText('raw_lhb_payload missing')).toBeInTheDocument();
    expect(screen.getByText('LHB feed incomplete')).toBeInTheDocument();
  });

  it('renders unavailable artifacts as non-clickable text and derives artifact section status from artifact health', async () => {
    renderResolvedPage(
      makeResponse({
        state: 'ready',
        selected_run: {
          ...makeResponse().selected_run!,
          artifact_health: 'missing',
          artifact_health_detail: {
            daily_review_json: 'healthy',
            operator_notes_md: 'missing'
          }
        },
        artifacts: [
          {
            key: 'daily_review_json',
            label: 'Daily Review JSON',
            kind: 'json',
            required: true,
            available: true,
            filename: 'daily_review_2026-06-20.json',
            content_type: 'application/json',
            url: '/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=daily_review_json'
          },
          {
            key: 'operator_notes_md',
            label: 'Operator Notes Markdown',
            kind: 'markdown',
            required: false,
            available: false,
            filename: null,
            content_type: 'text/markdown',
            url: '/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=operator_notes_md'
          }
        ]
      })
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Artifacts' })).toBeInTheDocument();
    });

    const artifactsSection = screen.getByRole('region', { name: 'Artifacts' });
    expect(within(artifactsSection).getByText('Status: partial')).toBeInTheDocument();
    expect(within(artifactsSection).getByRole('link', { name: 'Daily Review JSON' })).toHaveAttribute(
      'href',
      '/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=daily_review_json'
    );
    expect(within(artifactsSection).queryByRole('link', { name: 'Operator Notes Markdown' })).not.toBeInTheDocument();
    expect(within(artifactsSection).getByText('Operator Notes Markdown')).toBeInTheDocument();
  });

  it('renders a partial strategy summaries wrapper when strategy states are mixed between success and empty', async () => {
    renderResolvedPage(
      makeResponse({
        sections: {
          ...makeResponse().sections,
          strategy_summaries: {
            lhb: {
              strategy_id: 'lhb',
              status: 'success',
              warnings: [],
              summary: {},
              top_items: []
            },
            mid_trend: {
              strategy_id: 'mid_trend',
              status: 'empty',
              warnings: [],
              summary: {},
              top_items: []
            },
            technical_bottleneck: {
              strategy_id: 'technical_bottleneck',
              status: 'success',
              warnings: [],
              summary: {},
              top_items: []
            }
          }
        }
      })
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Strategy Summaries' })).toBeInTheDocument();
    });

    const strategySection = screen.getByRole('region', { name: 'Strategy Summaries' });
    expect(within(strategySection).getByText('Status: partial')).toBeInTheDocument();
  });
});
