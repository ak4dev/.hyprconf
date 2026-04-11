import React from 'react';
import { cn } from '@/lib/cn';
import styles from './Badge.module.css';

type BadgeVariant = 'default' | 'accent' | 'dark' | 'light' | 'ai';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ variant = 'default', className, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(styles.badge, styles[variant], className)}
        {...props}
      />
    );
  }
);
Badge.displayName = 'Badge';

export { Badge };
export type { BadgeProps, BadgeVariant };
