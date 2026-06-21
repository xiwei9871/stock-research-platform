import React from 'react';
import ReactDOM from 'react-dom/client';
import { DailyReviewLitePage } from './pages/DailyReviewLitePage';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <DailyReviewLitePage />
  </React.StrictMode>
);
