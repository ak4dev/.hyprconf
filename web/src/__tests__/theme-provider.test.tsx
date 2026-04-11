import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ThemeProvider, useTheme } from '@/lib/theme-provider';
import { defaultThemeName, themes } from '@/generated/themes';
import type { ReactNode } from 'react';

function wrapper({ children }: { children: ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.style.cssText = '';
  });

  it('provides default theme', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.themeName).toBe(defaultThemeName);
    expect(result.current.theme).toEqual(themes[defaultThemeName]);
  });

  it('setTheme updates current theme', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    const otherName = Object.keys(themes).find((n) => n !== defaultThemeName)!;

    act(() => {
      result.current.setTheme(otherName);
    });

    expect(result.current.themeName).toBe(otherName);
  });

  it('persists theme to localStorage', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    const otherName = Object.keys(themes).find((n) => n !== defaultThemeName)!;

    act(() => {
      result.current.setTheme(otherName);
    });

    expect(localStorage.getItem('hyprconf-theme')).toBe(otherName);
  });

  it('sets CSS custom properties on document', () => {
    renderHook(() => useTheme(), { wrapper });
    const root = document.documentElement;
    expect(root.style.getPropertyValue('--hc-bg')).toBe(themes[defaultThemeName]!.background);
    expect(root.style.getPropertyValue('--hc-accent')).toBe(themes[defaultThemeName]!.accent);
  });

  it('allThemes contains all themes', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(Object.keys(result.current.allThemes).length).toBe(Object.keys(themes).length);
  });

  it('falls back to default for invalid theme name', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });

    act(() => {
      result.current.setTheme('nonexistent-theme');
    });

    expect(result.current.themeName).toBe(defaultThemeName);
  });
});
