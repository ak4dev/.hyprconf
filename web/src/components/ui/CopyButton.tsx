import React from 'react';
import { Clipboard, Check } from 'lucide-react';
import { useCopyToClipboard } from '@/lib/hooks';
import { cn } from '@/lib/cn';
import styles from './CopyButton.module.css';

interface CopyButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  text: string;
}

const CopyButton = React.forwardRef<HTMLButtonElement, CopyButtonProps>(
  ({ text, className, ...props }, ref) => {
    const { copy, state } = useCopyToClipboard();

    return (
      <button
        ref={ref}
        type="button"
        className={cn(styles.button, state === 'success' && styles.success, className)}
        onClick={() => copy(text)}
        aria-label={state === 'success' ? 'Copied!' : 'Copy to clipboard'}
        {...props}
      >
        {state === 'success' ? <Check size={14} /> : <Clipboard size={14} />}
      </button>
    );
  }
);
CopyButton.displayName = 'CopyButton';

export { CopyButton };
export type { CopyButtonProps };
