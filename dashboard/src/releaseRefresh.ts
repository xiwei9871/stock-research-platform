type VisibilityEventTarget = EventTarget & {
  visibilityState: DocumentVisibilityState;
};

type ReleaseRefreshOptions = {
  currentReleaseId: string;
  windowTarget?: EventTarget;
  documentTarget?: VisibilityEventTarget;
  fetchRelease?: (input: string, init: RequestInit) => Promise<Response>;
  reload?: () => void;
  now?: () => number;
  releaseUrl?: string;
};

type ReleaseMetadata = {
  release_id?: unknown;
};

export function installReleaseRefresh({
  currentReleaseId,
  windowTarget = window,
  documentTarget = document,
  fetchRelease = (input, init) => fetch(input, init),
  reload = () => window.location.reload(),
  now = () => Date.now(),
  releaseUrl = '/release.json'
}: ReleaseRefreshOptions): () => void {
  const normalizedCurrentReleaseId = currentReleaseId.trim();
  if (!normalizedCurrentReleaseId) {
    return () => undefined;
  }

  let checkInFlight = false;
  let disposed = false;
  let reloadRequested = false;

  async function checkRelease() {
    if (checkInFlight || disposed || reloadRequested) return;
    checkInFlight = true;

    try {
      const separator = releaseUrl.includes('?') ? '&' : '?';
      const response = await fetchRelease(`${releaseUrl}${separator}t=${now()}`, {
        cache: 'no-store'
      });
      if (!response.ok || disposed) return;

      const metadata = (await response.json()) as ReleaseMetadata;
      const availableReleaseId =
        typeof metadata.release_id === 'string' ? metadata.release_id.trim() : '';
      if (
        !availableReleaseId ||
        availableReleaseId === normalizedCurrentReleaseId ||
        disposed ||
        reloadRequested
      ) {
        return;
      }

      reloadRequested = true;
      reload();
    } catch {
      // Release checks are best-effort; the next focus event retries.
    } finally {
      checkInFlight = false;
    }
  }

  const handleFocus = () => {
    void checkRelease();
  };
  const handleVisibilityChange = () => {
    if (documentTarget.visibilityState === 'visible') {
      void checkRelease();
    }
  };

  windowTarget.addEventListener('focus', handleFocus);
  documentTarget.addEventListener('visibilitychange', handleVisibilityChange);

  return () => {
    disposed = true;
    windowTarget.removeEventListener('focus', handleFocus);
    documentTarget.removeEventListener('visibilitychange', handleVisibilityChange);
  };
}
