import React from 'react';
import { cn } from '@/lib/cn';
import styles from './SectionHeading.module.css';

interface SectionHeadingProps extends React.HTMLAttributes<HTMLHeadingElement> {
  as?: 'h2' | 'h3' | 'h4';
}

const SectionHeading = React.forwardRef<HTMLHeadingElement, SectionHeadingProps>(
  ({ as: Tag = 'h2', className, id, ...props }, ref) => {
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
