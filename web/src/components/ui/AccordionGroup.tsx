import React, { createContext, useContext } from 'react';
import { cn } from '@/lib/cn';
import styles from './AccordionGroup.module.css';

interface AccordionContextValue {
  openItem: string | null;
  toggle: (value: string) => void;
}

const AccordionContext = createContext<AccordionContextValue>({
  openItem: null,
  toggle: () => {},
});

interface AccordionGroupProps extends React.HTMLAttributes<HTMLDivElement> {
  defaultOpen?: string;
}

function AccordionGroupRoot({ defaultOpen, className, children, ...props }: AccordionGroupProps) {
  const [openItem, setOpenItem] = React.useState<string | null>(defaultOpen ?? null);
  const toggle = React.useCallback(
    (value: string) => setOpenItem((prev) => (prev === value ? null : value)),
    []
  );

  return (
    <AccordionContext value={{ openItem, toggle }}>
      <div className={cn(styles.group, className)} {...props}>
        {children}
      </div>
    </AccordionContext>
  );
}

interface ItemProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
}

function Item({ value, className, children, ...props }: ItemProps) {
  const { openItem } = useContext(AccordionContext);
  const isOpen = openItem === value;

  return (
    <div
      className={cn(styles.item, isOpen && styles.itemOpen, className)}
      data-state={isOpen ? 'open' : 'closed'}
      {...props}
    >
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
          return React.cloneElement(child as React.ReactElement<{ value?: string }>, { value });
        }
        return child;
      })}
    </div>
  );
}

interface TriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value?: string;
}

function Trigger({ value, className, children, ...props }: TriggerProps) {
  const { openItem, toggle } = useContext(AccordionContext);
  const isOpen = value ? openItem === value : false;

  return (
    <button
      type="button"
      className={cn(styles.trigger, className)}
      aria-expanded={isOpen}
      onClick={() => value && toggle(value)}
      {...props}
    >
      <span>{children}</span>
      <span className={cn(styles.chevron, isOpen && styles.chevronOpen)}>▸</span>
    </button>
  );
}

interface ContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: string;
}

function Content({ value, className, children, ...props }: ContentProps) {
  const { openItem } = useContext(AccordionContext);
  const isOpen = value ? openItem === value : false;

  if (!isOpen) return null;

  return (
    <div className={cn(styles.content, className)} role="region" {...props}>
      {children}
    </div>
  );
}

export const AccordionGroup = Object.assign(AccordionGroupRoot, {
  Item,
  Trigger,
  Content,
});
