import { useEffect } from 'react';

import { DashboardAuthRoot } from './components/DashboardAuthRoot';
import { installReleaseRefresh } from './releaseRefresh';

export function App() {
  useEffect(
    () =>
      installReleaseRefresh({
        currentReleaseId: import.meta.env.VITE_RELEASE_ID ?? ''
      }),
    []
  );

  return <DashboardAuthRoot />;
}
