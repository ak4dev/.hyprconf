import React from 'react';
import { cn } from '@/lib/cn';
import styles from './KeyboardKey.module.css';

interface KeyboardKeyProps extends React.HTMLAttributes<HTMLSpanElement> {
  keys: string[];
}

const KeyboardKey = React.forwardRef<HTMLSpanElement, KeyboardKeyProps>(
  ({ keys, className, ...props }, ref) => {
    return (
      <span ref={ref} className={cn(styles.combo, className)} {...props}>
        {keys.map((key, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span className={styles.separator}>+</span>}
            <kbd className={styles.key}>{key}</kbd>
          </React.Fragment>
        ))}
      </span>
    );
  }
);
KeyboardKey.displayName = 'KeyboardKey';

export { KeyboardKey };
export type { KeyboardKeyProps };
