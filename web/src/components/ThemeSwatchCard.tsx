import React from 'react';
import { Badge } from '@/components/ui';
import { useTheme } from '@/lib/theme-provider';
import { cn } from '@/lib/cn';
import type { Theme } from '@/generated/themes';
import styles from './ThemeSwatchCard.module.css';

interface ThemeSwatchCardProps extends React.HTMLAttributes<HTMLButtonElement> {
  themeName: string;
  theme: Theme;
}

const ThemeSwatchCard = React.forwardRef<HTMLButtonElement, ThemeSwatchCardProps>(
  ({ themeName, theme, className, ...props }, ref) => {
    const { themeName: currentTheme, setTheme } = useTheme();
    const isActive = currentTheme === themeName;
    const isAi = themeName.startsWith('ai:');

    const colours = [
      theme.background,
      theme.foreground,
      theme.accent,
      theme.comment,
      theme.purple ?? theme.cyan ?? theme.green ?? theme.accent,
    ];

    return (
      <button
        ref={ref}
        type="button"
        className={cn(styles.card, isActive && styles.active, className)}
        onClick={() => setTheme(themeName)}
        aria-pressed={isActive}
        aria-label={`Apply ${themeName} theme`}
        {...props}
      >
        <div className={styles.header}>
          <span className={styles.name}>{themeName}</span>
          <Badge variant={theme.appearance === 'dark' ? 'dark' : 'light'}>
            {theme.appearance === 'dark' ? '☾' : '☀'}
          </Badge>
          {isAi && <Badge variant="ai">AI</Badge>}
        </div>
        <div className={styles.swatches}>
          {colours.map((color, i) => (
            <div
              key={i}
              className={styles.swatch}
              style={{ backgroundColor: color }}
              aria-hidden
            />
          ))}
        </div>
        {isActive && <span className={styles.activeLabel}>Active</span>}
      </button>
    );
  }
);
ThemeSwatchCard.displayName = 'ThemeSwatchCard';

export { ThemeSwatchCard };
