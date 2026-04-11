import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { Card } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { Feature } from '@/content';
import styles from './FeatureCard.module.css';

interface FeatureCardProps extends React.HTMLAttributes<HTMLDivElement> {
  feature: Feature;
}

const FeatureCard = React.forwardRef<HTMLDivElement, FeatureCardProps>(
  ({ feature, className, ...props }, ref) => {
    const navigate = useNavigate();
    const Icon = feature.icon;
    const isLinkable = !!feature.route;

    const handleClick = () => {
      if (feature.route) navigate(feature.route);
    };

    return (
      <Card
        ref={ref}
        variant={isLinkable ? 'interactive' : 'default'}
        className={cn(styles.card, className)}
        onClick={isLinkable ? handleClick : undefined}
        role={isLinkable ? 'link' : undefined}
        tabIndex={isLinkable ? 0 : undefined}
        onKeyDown={
          isLinkable
            ? (e: React.KeyboardEvent) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleClick();
                }
              }
            : undefined
        }
        {...props}
      >
        <div className={styles.iconWrapper}>
          <Icon size={20} />
        </div>
        <h3 className={styles.title}>{feature.title}</h3>
        <p className={styles.description}>{feature.description}</p>
        {isLinkable && (
          <span className={styles.arrow} aria-hidden>
            <ArrowRight size={16} />
          </span>
        )}
      </Card>
    );
  }
);
FeatureCard.displayName = 'FeatureCard';

export { FeatureCard };
