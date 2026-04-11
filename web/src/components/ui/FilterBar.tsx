import React from 'react';
import { cn } from '@/lib/cn';
import styles from './FilterBar.module.css';

interface FilterOption {
  label: string;
  value: string;
}

interface FilterBarProps extends React.HTMLAttributes<HTMLDivElement> {
  options: FilterOption[];
  activeValue: string;
  onValueChange: (value: string) => void;
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
}

const FilterBar = React.forwardRef<HTMLDivElement, FilterBarProps>(
  (
    {
      options,
      activeValue,
      onValueChange,
      searchPlaceholder,
      searchValue,
      onSearchChange,
      className,
      ...props
    },
    ref
  ) => {
    return (
      <div ref={ref} className={cn(styles.bar, className)} {...props}>
        <div className={styles.pills} role="radiogroup">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={activeValue === opt.value}
              className={cn(styles.pill, activeValue === opt.value && styles.pillActive)}
              onClick={() => onValueChange(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {onSearchChange && (
          <input
            type="search"
            className={styles.search}
            placeholder={searchPlaceholder ?? 'Search…'}
            value={searchValue ?? ''}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Search"
          />
        )}
      </div>
    );
  }
);
FilterBar.displayName = 'FilterBar';

export { FilterBar };
export type { FilterBarProps, FilterOption };
