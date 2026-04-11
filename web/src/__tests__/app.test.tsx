import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@/lib/theme-provider';
import { AppLayout } from '@/components/layout/AppLayout';
import Landing from '@/pages/Landing';

function renderWithRouter(route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ThemeProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Landing />} />
          </Route>
        </Routes>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe('App', () => {
  it('renders without crashing', () => {
    renderWithRouter();
    expect(document.body).toBeDefined();
  });
});

describe('Landing page', () => {
  it('renders hero title', () => {
    renderWithRouter();
    expect(screen.getAllByText(/hyprconf/i).length).toBeGreaterThan(0);
  });

  it('renders install command', () => {
    renderWithRouter();
    expect(screen.getByText(/curl -fsSL hyprconf\.sh/)).toBeInTheDocument();
  });

  it('renders feature cards', () => {
    renderWithRouter();
    expect(screen.getByText('Theme Engine')).toBeInTheDocument();
    expect(screen.getAllByText('Keybindings').length).toBeGreaterThan(0);
  });

  it('has GitHub link', () => {
    renderWithRouter();
    const ghLinks = screen.getAllByLabelText(/github/i);
    expect(ghLinks.length).toBeGreaterThan(0);
  });

  it('renders desktop screenshot', () => {
    renderWithRouter();
    const img = screen.getByAltText('.hyprconf desktop with TUI');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', '/images/hyprconf.webp');
    expect(img).toHaveAttribute('loading', 'lazy');
  });
});
