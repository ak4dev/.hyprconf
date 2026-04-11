import { SectionHeading, Card, CodeBlock } from '@/components/ui';
import { INSTALL_COMMAND, INSTALL_MODES } from '@/content';
import styles from './Install.module.css';

export default function Install() {
  return (
    <div className={styles.page}>
      <SectionHeading id="installation">Installation</SectionHeading>
      <p className={styles.intro}>
        Three install modes — pick the one that fits your setup.
        All modes use the same one-line command:
      </p>

      <div className={styles.installBlock}>
        <CodeBlock language="bash" prompt>
          {INSTALL_COMMAND}
        </CodeBlock>
      </div>

      <SectionHeading id="requirements" level={2}>
        Requirements
      </SectionHeading>
      <ul className={styles.list}>
        <li>Arch Linux (or Arch-based distro for Dotfiles Only / CLI Only)</li>
        <li>Hyprland (installed automatically in Full Arch Install)</li>
        <li>Internet connection</li>
      </ul>

      <div className={styles.modes}>
        {INSTALL_MODES.map((mode) => (
          <Card key={mode.title} className={styles.modeCard}>
            <SectionHeading id={mode.title.toLowerCase().replace(/\s+/g, '-')} level={3}>
              {mode.title}
            </SectionHeading>
            <p className={styles.modeDesc}>{mode.description}</p>
            <ol className={styles.steps}>
              {mode.steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </Card>
        ))}
      </div>

      <SectionHeading id="post-install" level={2}>
        Post-Install
      </SectionHeading>
      <div className={styles.prose}>
        <p>
          After installation, run <code>hyprconf sync</code> to apply all configuration
          changes. This is also how you update an existing install — sync patches
          hardware config, services, and packages idempotently.
        </p>
        <p>
          Choose your first theme with <code>hyprconf theme --pick</code> or explore
          the gallery on the <a href="/themes">Themes page</a>.
        </p>
      </div>
    </div>
  );
}
