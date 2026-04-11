import React from 'react';
import { cn } from '@/lib/cn';
import styles from './SectionHeading.module.css';

interface SectionHeadingProps extends React.HTMLAttributes<HTMLHeadingElement> {
  as?: 'h2' | 'h3' | 'h4';
  level?: 2 | 3 | 4;
}

const SectionHeading = React.forwardRef<HTMLHeadingElement, SectionHeadingProps>(
  ({ as, level, className, id, ...props }, ref) => {
    const Tag = as ?? (level ? (`h${level}` as 'h2' | 'h3' | 'h4') : 'h2');
    return (
      <Tag
        ref={ref}
        id={id}
        className={cn(styles.heading, className)}
        {...props}
      />
    );
  }
);
SectionHeading.displayName = 'SectionHeading';

export { SectionHeading };
export type { SectionHeadingProps };
