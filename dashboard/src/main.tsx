import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { PublicSnapshotPage } from './components/PublicSnapshotPage';
import './styles.css';

const path = window.location.pathname.replace(/\/+$/, '') || '/';
const viteEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
const processEnv = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
const publicSnapshotOnlyValue = viteEnv?.VITE_PUBLIC_SNAPSHOT_ONLY ?? processEnv?.VITE_PUBLIC_SNAPSHOT_ONLY;
const publicSnapshotOnly = String(publicSnapshotOnlyValue || '').toLowerCase() === 'true';
const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);

root.render(
  <React.StrictMode>
    {publicSnapshotOnly || path === '/public' ? <PublicSnapshotPage /> : <App />}
  </React.StrictMode>
);
