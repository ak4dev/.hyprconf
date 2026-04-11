import { GitHubLogoIcon } from '@radix-ui/react-icons';
import { Card, CodeBlock } from '@/components/ui';
import { FeatureCard } from '@/components/FeatureCard';
import {
  GITHUB_REPO,
  PROJECT_TAGLINE,
  PROJECT_DESCRIPTION,
  INSTALL_COMMAND,
  FEATURES,
} from '@/content';
import styles from './Landing.module.css';

export default function Landing() {
  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroGlow}>
          <h1 className={styles.heroTitle}>hyprconf</h1>
          <p className={styles.tagline}>{PROJECT_TAGLINE}</p>
          <p className={styles.description}>{PROJECT_DESCRIPTION}</p>

          <div className={styles.actions}>
            <div className={styles.installBlock}>
              <CodeBlock language="bash" prompt>
                {INSTALL_COMMAND}
              </CodeBlock>
            </div>
            <a
              href={GITHUB_REPO}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.ghButton}
            >
              <GitHubLogoIcon width={16} height={16} />
              <span>View on GitHub</span>
            </a>
          </div>
        </div>
      </section>

      <section className={styles.features}>
        <div className={styles.featureGrid}>
          {FEATURES.map((f) => (
            <FeatureCard key={f.title} feature={f} />
          ))}
        </div>
      </section>
    </div>
  );
}
