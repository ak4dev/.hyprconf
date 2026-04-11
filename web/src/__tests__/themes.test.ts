import { describe, it, expect } from 'vitest';
import {
  themes,
  themeNames,
  communityThemeNames,
  aiThemeNames,
  defaultThemeName,
  themeCount,
  type Theme,
} from '@/generated/themes';

const REQUIRED_KEYS: (keyof Theme)[] = ['background', 'foreground', 'accent', 'comment', 'appearance'];

describe('generated themes', () => {
  it('has correct total count', () => {
    expect(themeCount).toBe(Object.keys(themes).length);
    expect(themeNames.length).toBe(themeCount);
  });

  it('community + ai = total', () => {
    expect(communityThemeNames.length + aiThemeNames.length).toBe(themeCount);
  });

  it('default theme exists', () => {
    expect(themes[defaultThemeName]).toBeDefined();
  });

  it('all AI themes start with "ai:"', () => {
    for (const name of aiThemeNames) {
      expect(name.startsWith('ai:')).toBe(true);
    }
  });

  it('no community themes start with "ai:"', () => {
    for (const name of communityThemeNames) {
      expect(name.startsWith('ai:')).toBe(false);
    }
  });

  describe.each(themeNames)('theme "%s"', (name) => {
    it('has all required keys', () => {
      const t = themes[name]!;
      for (const key of REQUIRED_KEYS) {
        expect(t[key]).toBeDefined();
        expect(typeof t[key]).toBe('string');
        expect((t[key] as string).length).toBeGreaterThan(0);
      }
    });

    it('has valid appearance', () => {
      const t = themes[name]!;
      expect(['dark', 'light']).toContain(t.appearance);
    });

    it('has valid hex colours for required colour keys', () => {
      const t = themes[name]!;
      const hexRegex = /^#[0-9a-fA-F]{6}$/;
      for (const key of ['background', 'foreground', 'accent', 'comment'] as const) {
        expect(t[key]).toMatch(hexRegex);
      }
    });
  });
});
