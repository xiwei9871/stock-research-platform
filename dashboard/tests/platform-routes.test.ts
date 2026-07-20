import { describe, expect, it } from 'vitest';
import {
  WORKSPACE_PATHS,
  parsePlatformLocation,
  pathForWorkspace,
  stockCodeToAssetId,
  stockPath
} from '../src/navigation/platformRoutes';

describe('platform routes', () => {
  it('parses the home and every primary workspace path', () => {
    for (const [workspace, canonicalPath] of Object.entries(WORKSPACE_PATHS)) {
      expect(parsePlatformLocation(canonicalPath, '')).toMatchObject({ workspace, canonicalPath });
      expect(pathForWorkspace(workspace as keyof typeof WORKSPACE_PATHS)).toBe(canonicalPath);
    }
  });

  it('keeps theme research detail paths route-backed', () => {
    expect(parsePlatformLocation('/theme-research/ai_power_value_capture_v1/nodes', '')).toMatchObject({
      workspace: 'themeResearch',
      canonicalPath: '/theme-research/ai_power_value_capture_v1/nodes'
    });
    expect(parsePlatformLocation('/theme-research/catalog/grid%20storage', '')).toMatchObject({
      workspace: 'themeResearch',
      canonicalPath: '/theme-research/catalog/grid%20storage'
    });
  });

  it('canonicalizes the legacy technology-bottleneck review route', () => {
    expect(parsePlatformLocation('/tech-bottleneck/watchlist-review', '')).toMatchObject({
      workspace: 'techBottleneckReviewUniverse',
      canonicalPath: '/research/tech-bottleneck/review-universe'
    });
  });

  it('parses canonical and compatible stock routes with normalized asset ids', () => {
    expect(parsePlatformLocation('/stock/600519.SH', '?source=search&q=600519')).toMatchObject({
      workspace: 'stock',
      assetId: '600519.SH',
      canonicalPath: '/stock/600519.SH',
      sourceWorkspace: 'search',
      query: '600519'
    });
    expect(parsePlatformLocation('/stock/300760', '')).toMatchObject({
      workspace: 'stock',
      assetId: '300760.SZ',
      canonicalPath: '/stock/300760.SZ'
    });
    expect(parsePlatformLocation('/tech-bottleneck/stock/300760.SZ', '?source=theme_research')).toMatchObject({
      workspace: 'stock',
      assetId: '300760.SZ',
      canonicalPath: '/stock/300760.SZ',
      sourceWorkspace: 'themeResearch'
    });
  });

  it('decodes known handoff fields and ignores unknown query fields', () => {
    expect(
      parsePlatformLocation(
        '/stock/600519',
        '?source=research_reports&q=%E8%B4%B5%E5%B7%9E%E8%8C%85%E5%8F%B0&match_reason=title%20match&unknown=drop-me'
      )
    ).toEqual({
      workspace: 'stock',
      assetId: '600519.SH',
      canonicalPath: '/stock/600519.SH',
      sourceWorkspace: 'researchReports',
      query: '贵州茅台',
      matchReason: 'title match'
    });
    expect(
      parsePlatformLocation(
        '/research-reports',
        '?q=%E5%8D%8A%E5%AF%BC%E4%BD%93&report_id=report%3A42&unknown=drop-me'
      )
    ).toEqual({
      workspace: 'researchReports',
      canonicalPath: '/research-reports',
      query: '半导体',
      reportId: 'report:42'
    });
  });

  it('normalizes stock codes and builds canonical stock paths', () => {
    expect(stockCodeToAssetId('600519')).toBe('600519.SH');
    expect(stockCodeToAssetId('300760')).toBe('300760.SZ');
    expect(stockCodeToAssetId('600519.sh')).toBe('600519.SH');
    expect(stockPath('300760')).toBe('/stock/300760.SZ');
    expect(stockPath('CN:SH:600519')).toBe('/stock/CN%3ASH%3A600519');
  });

  it('falls back invalid paths to home', () => {
    expect(parsePlatformLocation('/not-a-workspace', '?source=search&q=ignored')).toEqual({
      workspace: 'home',
      canonicalPath: '/'
    });
  });
});
