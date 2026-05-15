import { useState, useEffect, useMemo, useRef } from 'react';
import { ChevronDown, Palette } from 'lucide-react';
import { useTheme } from '@/lib/theme-provider';
import { themeNames, communityThemeNames, aiThemeNames } from '@/generated/themes';
import { cn } from '@/lib/cn';
import styles from './ThemePicker.module.css';

type FilterValue = 'all' | 'dark' | 'light' | 'ai';

export function ThemePicker() {
  const { themeName, setTheme, allThemes } = useTheme();
  const [isOpen, setIsOpen] = useState(false);
  const [filter, setFilter] = useState<FilterValue>('all');
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    dropdownRef.current?.focus();
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  const filteredNames = useMemo(() => {
    switch (filter) {
      case 'dark':
        return themeNames.filter((n) => allThemes[n]?.appearance === 'dark');
      case 'light':
        return themeNames.filter((n) => allThemes[n]?.appearance === 'light');
      case 'ai':
        return aiThemeNames;
      default:
        return [...communityThemeNames, ...aiThemeNames];
    }
  }, [filter, allThemes]);

  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-label="Select theme"
      >
        <Palette size={16} />
        <span className={styles.triggerLabel}>{themeName}</span>
        <ChevronDown size={14} className={cn(styles.chevron, isOpen && styles.chevronOpen)} />
      </button>

      {isOpen && (
        <>
          <div className={styles.backdrop} onClick={() => setIsOpen(false)} aria-hidden />
          <div ref={dropdownRef} className={styles.dropdown} role="listbox" aria-label="Theme list" tabIndex={-1}>
            <div className={styles.filters}>
              {(['all', 'dark', 'light', 'ai'] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  className={cn(styles.filterPill, filter === f && styles.filterActive)}
                  onClick={() => setFilter(f)}
                >
                  {f === 'ai' ? 'AI' : f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
            <div className={styles.list}>
              {filteredNames.map((name) => {
                const t = allThemes[name];
                if (!t) return null;
                return (
                  <button
                    key={name}
                    type="button"
                    role="option"
                    aria-selected={name === themeName}
                    className={cn(styles.option, name === themeName && styles.optionActive)}
                    onClick={() => {
                      setTheme(name);
                      setIsOpen(false);
                    }}
                  >
                    <div className={styles.optionSwatches}>
                      <span className={styles.miniSwatch} style={{ background: t.background }} />
                      <span className={styles.miniSwatch} style={{ background: t.accent }} />
                      <span className={styles.miniSwatch} style={{ background: t.foreground }} />
                    </div>
                    <span className={styles.optionName}>{name}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
