import { useState, useMemo } from 'react';
import { SectionHeading, FilterBar } from '@/components/ui';
import { ThemeSwatchCard } from '@/components/ThemeSwatchCard';
import {
  themes,
  themeNames,
  communityThemeNames,
  aiThemeNames,
  themeCount,
} from '@/generated/themes';
import { useTheme } from '@/lib/theme-provider';
import styles from './Themes.module.css';

type FilterValue = 'all' | 'dark' | 'light' | 'ai';

const filterOptions = [
  { label: 'All', value: 'all' },
  { label: 'Dark', value: 'dark' },
  { label: 'Light', value: 'light' },
  { label: 'AI Original', value: 'ai' },
];

export default function Themes() {
  const { themeName } = useTheme();
  const [filter, setFilter] = useState<FilterValue>('all');
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    let names: string[];
    switch (filter) {
      case 'dark':
        names = themeNames.filter((n) => themes[n]?.appearance === 'dark');
        break;
      case 'light':
        names = themeNames.filter((n) => themes[n]?.appearance === 'light');
        break;
      case 'ai':
        names = [...aiThemeNames];
        break;
      default:
        names = [...communityThemeNames, ...aiThemeNames];
    }
    if (search) {
      const q = search.toLowerCase();
      names = names.filter((n) => n.toLowerCase().includes(q));
    }
    return names;
  }, [filter, search]);

  return (
    <div className={styles.page}>
      <SectionHeading id="theme-gallery">
        Theme Gallery <span className={styles.count}>({themeCount})</span>
      </SectionHeading>

      <p className={styles.intro}>
        Currently viewing: <strong>{themeName}</strong>. Click any theme to apply it instantly.
      </p>

      <FilterBar
        options={filterOptions}
        activeValue={filter}
        onValueChange={(v) => setFilter(v as FilterValue)}
        searchPlaceholder="Search themes…"
        searchValue={search}
        onSearchChange={setSearch}
      />

      <div className={styles.grid}>
        {filtered.map((name) => {
          const t = themes[name];
          if (!t) return null;
          return <ThemeSwatchCard key={name} themeName={name} theme={t} />;
        })}
        {filtered.length === 0 && (
          <p className={styles.empty}>No themes match your search.</p>
        )}
      </div>

      <SectionHeading id="how-themes-work" level={2}>
        How Themes Work
      </SectionHeading>
      <div className={styles.prose}>
        <p>
          Themes are JSON files in the dotfiles repository. Each theme defines a colour palette
          (background, foreground, accent, comment, and optional extended colours) plus an
          appearance flag (dark/light).
        </p>
        <p>
          When you switch themes via <code>hyprconf theme</code>, the CLI cascades the palette
          across Hyprland borders, Waybar, Kitty, VS Code, Firefox, hyprlock, and wallpaper — all
          in one command.
        </p>
        <p>
          This website mirrors those same theme files. The theme picker in the top nav applies
          colours as CSS custom properties — every component on the site responds instantly.
        </p>
      </div>
    </div>
  );
}
