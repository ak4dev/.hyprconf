import React from 'react';
import { CopyButton } from './CopyButton';
import { cn } from '@/lib/cn';
import styles from './CodeBlock.module.css';

interface CodeBlockProps extends React.HTMLAttributes<HTMLDivElement> {
  code?: string;
  language?: string;
  showPrompt?: boolean;
  prompt?: boolean;
  copyable?: boolean;
}

const CodeBlock = React.forwardRef<HTMLDivElement, CodeBlockProps>(
  ({ code, language, showPrompt = false, prompt = false, copyable = true, className, children, ...props }, ref) => {
    const text = code ?? (typeof children === 'string' ? children : '');
    const shouldShowPrompt = showPrompt || prompt;
    return (
      <div ref={ref} className={cn(styles.wrapper, className)} {...props}>
        {language && <span className={styles.language}>{language}</span>}
        {copyable && (
          <div className={styles.copyWrapper}>
            <CopyButton text={text} />
          </div>
        )}
        <pre className={styles.pre}>
          <code className={styles.code}>
            {shouldShowPrompt && <span className={styles.prompt}>$ </span>}
            {text}
          </code>
        </pre>
      </div>
    );
  }
);
CodeBlock.displayName = 'CodeBlock';

export { CodeBlock };
export type { CodeBlockProps };
