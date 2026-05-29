import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from '../src/App';

describe('dashboard app shell', () => {
  it('renders the stock research shell title', () => {
    render(<App />);

    expect(screen.getByText('Stock Research')).toBeVisible();
  });
});
