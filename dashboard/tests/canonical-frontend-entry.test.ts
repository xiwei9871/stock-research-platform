/// <reference types="vite/client" />

import { render } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { cleanupReleaseRefresh, installReleaseRefresh } = vi.hoisted(() => ({
  cleanupReleaseRefresh: vi.fn(),
  installReleaseRefresh: vi.fn()
}));

vi.mock('../src/releaseRefresh', () => ({ installReleaseRefresh }));
vi.mock('../src/components/DashboardAuthRoot', () => ({
  DashboardAuthRoot: () => null
}));

import { App } from '../src/App';

beforeEach(() => {
  cleanupReleaseRefresh.mockReset();
  installReleaseRefresh.mockReset();
  installReleaseRefresh.mockReturnValue(cleanupReleaseRefresh);
});

describe('canonical frontend entry', () => {
  it('does not keep legacy public snapshot frontend entrypoints', () => {
    const legacyEntryModules = import.meta.glob([
      '../public-snapshot.html',
      '../public.html',
      '../src/public-main.tsx',
      '../src/components/PublicSnapshotPage.tsx',
      '../src/components/OpsSnapshotPanel.tsx',
      '../src/components/OpsStagesPanel.tsx',
      '../src/components/PublicNewsPanel.tsx'
    ]);

    expect(Object.keys(legacyEntryModules)).toEqual([]);
  });

  it('installs and cleans up release refresh detection at the application root', () => {
    const view = render(createElement(App));

    expect(installReleaseRefresh).toHaveBeenCalledWith({
      currentReleaseId: import.meta.env.VITE_RELEASE_ID ?? ''
    });

    view.unmount();
    expect(cleanupReleaseRefresh).toHaveBeenCalledTimes(1);
  });
});
