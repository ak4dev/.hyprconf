import React from 'react';
import { cn } from '@/lib/cn';
import styles from './Card.module.css';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  as?: React.ElementType;
  variant?: 'default' | 'interactive' | 'glass';
  glow?: boolean;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ as: Comp = 'div', variant = 'default', glow = false, className, ...props }, ref) => {
    return (
      <Comp
        ref={ref}
        className={cn(styles.card, styles[variant], glow && styles.glow, className)}
        {...props}
      />
    );
  }
);
Card.displayName = 'Card';

export { Card };
export type { CardProps };
