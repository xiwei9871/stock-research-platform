/// <reference types="vite/client" />

import { describe, expect, it } from 'vitest';

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
});
