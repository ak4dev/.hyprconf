import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useTransition,
  type ReactNode,
} from 'react';
import { themes, defaultThemeName, type Theme } from '@/generated/themes';

interface ThemeContextValue {
  theme: Theme;
  themeName: string;
  setTheme: (name: string) => void;
  allThemes: typeof themes;
  isPending: boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = 'hyprconf-theme';

const COLOUR_KEYS = [
  'bg', 'fg', 'accent', 'comment',
  'red', 'green', 'yellow', 'orange', 'pink', 'purple', 'cyan',
] as const;

const THEME_KEY_MAP: Record<string, keyof Theme> = {
  bg: 'background',
  fg: 'foreground',
  accent: 'accent',
  comment: 'comment',
  red: 'red',
  green: 'green',
  yellow: 'yellow',
  orange: 'orange',
  pink: 'pink',
  purple: 'purple',
  cyan: 'cyan',
};

function applyThemeToDOM(theme: Theme): void {
  const root = document.documentElement;
  for (const key of COLOUR_KEYS) {
    const themeKey = THEME_KEY_MAP[key];
    if (themeKey) {
      const value = theme[themeKey] as string | undefined;
      if (value) {
        root.style.setProperty(`--hc-${key}`, value);
      }
    }
  }
}

function resolveTheme(name: string): { name: string; theme: Theme } {
  if (themes[name]) {
    return { name, theme: themes[name]! };
  }
  return { name: defaultThemeName, theme: themes[defaultThemeName]! };
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeName, setThemeNameState] = useState<string>(() => {
    if (typeof window === 'undefined') return defaultThemeName;
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored && themes[stored] ? stored : defaultThemeName;
  });

  const [isPending, startTransition] = useTransition();

  const { theme } = resolveTheme(themeName);

  useEffect(() => {
    applyThemeToDOM(theme);
  }, [theme]);

  const setTheme = useCallback(
    (name: string) => {
      startTransition(() => {
        const resolved = resolveTheme(name);
        setThemeNameState(resolved.name);
        localStorage.setItem(STORAGE_KEY, resolved.name);
      });
    },
    [startTransition]
  );

  return (
    <ThemeContext value={{ theme, themeName, setTheme, allThemes: themes, isPending }}>
      {children}
    </ThemeContext>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
