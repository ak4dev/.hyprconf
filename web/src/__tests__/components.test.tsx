import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '@/lib/theme-provider';

import { Badge } from '@/components/ui/Badge';
import { KeyboardKey } from '@/components/ui/KeyboardKey';
import { SectionHeading } from '@/components/ui/SectionHeading';
import { PageSkeleton } from '@/components/PageSkeleton';

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <ThemeProvider>{children}</ThemeProvider>
    </MemoryRouter>
  );
}

describe('Badge', () => {
  it('renders text', () => {
    render(<Badge>Test</Badge>, { wrapper: Wrapper });
    expect(screen.getByText('Test')).toBeInTheDocument();
  });

  it('applies variant class', () => {
    const { container } = render(<Badge variant="accent">Accent</Badge>, { wrapper: Wrapper });
    expect(container.firstChild).toHaveAttribute('class');
    expect(screen.getByText('Accent')).toBeInTheDocument();
  });
});

describe('KeyboardKey', () => {
  it('renders keys with separators', () => {
    render(<KeyboardKey keys={['Super', 'Return']} />, { wrapper: Wrapper });
    const kbds = screen.getAllByText(/Super|Return/);
    expect(kbds).toHaveLength(2);
    expect(screen.getByText('+')).toBeInTheDocument();
  });

  it('renders single key without separator', () => {
    render(<KeyboardKey keys={['Escape']} />, { wrapper: Wrapper });
    expect(screen.getByText('Escape')).toBeInTheDocument();
    expect(screen.queryByText('+')).not.toBeInTheDocument();
  });
});

describe('SectionHeading', () => {
  it('renders with id for scroll-spy', () => {
    render(<SectionHeading id="test-section">Test</SectionHeading>, { wrapper: Wrapper });
    const heading = screen.getByText('Test');
    expect(heading.closest('[id="test-section"]') || heading).toHaveAttribute('id', 'test-section');
  });
});

describe('PageSkeleton', () => {
  it('renders loading skeleton', () => {
    render(<PageSkeleton />, { wrapper: Wrapper });
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
