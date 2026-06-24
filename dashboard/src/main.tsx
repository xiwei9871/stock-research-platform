import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { PublicSnapshotPage } from './components/PublicSnapshotPage';
import './styles.css';

const path = window.location.pathname.replace(/\/+$/, '') || '/';
const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);

root.render(
  <React.StrictMode>
    {path === '/public' ? <PublicSnapshotPage /> : <App />}
  </React.StrictMode>
);
