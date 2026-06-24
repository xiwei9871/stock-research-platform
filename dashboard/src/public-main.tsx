import React from 'react';
import ReactDOM from 'react-dom/client';
import { PublicSnapshotPage } from './components/PublicSnapshotPage';
import './styles.css';

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);

root.render(
  <React.StrictMode>
    <PublicSnapshotPage />
  </React.StrictMode>
);
