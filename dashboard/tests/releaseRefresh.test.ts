import { describe, expect, it, vi } from 'vitest';

import { installReleaseRefresh } from '../src/releaseRefresh';

class VisibilityTarget extends EventTarget {
  visibilityState: DocumentVisibilityState = 'visible';
}

function jsonResponse(payload: unknown, ok = true): Response {
  return {
    ok,
    json: vi.fn().mockResolvedValue(payload)
  } as unknown as Response;
}

function createHarness(currentReleaseId = 'release-a') {
  const windowTarget = new EventTarget();
  const documentTarget = new VisibilityTarget();
  const fetchRelease = vi.fn().mockResolvedValue(jsonResponse({ release_id: currentReleaseId }));
  const reload = vi.fn();
  const cleanup = installReleaseRefresh({
    currentReleaseId,
    windowTarget,
    documentTarget,
    fetchRelease,
    reload,
    now: () => 1234
  });

  return { cleanup, documentTarget, fetchRelease, reload, windowTarget };
}

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe('installReleaseRefresh', () => {
  it('does not install checks when the embedded release id is empty', async () => {
    const harness = createHarness('');

    harness.windowTarget.dispatchEvent(new Event('focus'));
    harness.documentTarget.dispatchEvent(new Event('visibilitychange'));
    await flushPromises();

    expect(harness.fetchRelease).not.toHaveBeenCalled();
    expect(harness.reload).not.toHaveBeenCalled();
  });

  it('checks cache-busted metadata on focus and keeps a matching release', async () => {
    const harness = createHarness();

    harness.windowTarget.dispatchEvent(new Event('focus'));
    await flushPromises();

    expect(harness.fetchRelease).toHaveBeenCalledWith('/release.json?t=1234', {
      cache: 'no-store'
    });
    expect(harness.reload).not.toHaveBeenCalled();
  });

  it('reloads once when a different non-empty release is available', async () => {
    const harness = createHarness();
    harness.fetchRelease.mockResolvedValue(jsonResponse({ release_id: 'release-b' }));

    harness.windowTarget.dispatchEvent(new Event('focus'));
    await flushPromises();
    harness.windowTarget.dispatchEvent(new Event('focus'));
    await flushPromises();

    expect(harness.fetchRelease).toHaveBeenCalledTimes(1);
    expect(harness.reload).toHaveBeenCalledTimes(1);
  });

  it('checks only when a visibility change makes the document visible', async () => {
    const harness = createHarness();
    harness.documentTarget.visibilityState = 'hidden';

    harness.documentTarget.dispatchEvent(new Event('visibilitychange'));
    await flushPromises();
    expect(harness.fetchRelease).not.toHaveBeenCalled();

    harness.documentTarget.visibilityState = 'visible';
    harness.documentTarget.dispatchEvent(new Event('visibilitychange'));
    await flushPromises();
    expect(harness.fetchRelease).toHaveBeenCalledTimes(1);
  });

  it('deduplicates overlapping focus and visibility checks', async () => {
    let resolveFetch: ((response: Response) => void) | undefined;
    const harness = createHarness();
    harness.fetchRelease.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        })
    );

    harness.windowTarget.dispatchEvent(new Event('focus'));
    harness.documentTarget.dispatchEvent(new Event('visibilitychange'));

    expect(harness.fetchRelease).toHaveBeenCalledTimes(1);
    resolveFetch?.(jsonResponse({ release_id: 'release-a' }));
    await flushPromises();
  });

  it('ignores malformed metadata and retries after request failures', async () => {
    const harness = createHarness();
    harness.fetchRelease
      .mockResolvedValueOnce(jsonResponse({ release_id: '' }))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(jsonResponse({ release_id: 'release-b' }));

    harness.windowTarget.dispatchEvent(new Event('focus'));
    await flushPromises();
    harness.windowTarget.dispatchEvent(new Event('focus'));
    await flushPromises();
    harness.windowTarget.dispatchEvent(new Event('focus'));
    await flushPromises();

    expect(harness.fetchRelease).toHaveBeenCalledTimes(3);
    expect(harness.reload).toHaveBeenCalledTimes(1);
  });

  it('removes both listeners during cleanup', async () => {
    const harness = createHarness();

    harness.cleanup();
    harness.windowTarget.dispatchEvent(new Event('focus'));
    harness.documentTarget.dispatchEvent(new Event('visibilitychange'));
    await flushPromises();

    expect(harness.fetchRelease).not.toHaveBeenCalled();
  });
});
