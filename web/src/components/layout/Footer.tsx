import { NavLink } from 'react-router-dom';
import { GitHubLogoIcon } from '@radix-ui/react-icons';
import { routes } from '@/routes';
import { GITHUB_REPO, VERSION } from '@/content';
import { cn } from '@/lib/cn';
import styles from './Footer.module.css';

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <div className={styles.col}>
          <span className={styles.brand}>
            <span className={styles.dot}>.</span>hyprconf
          </span>
          <span className={styles.version}>v{VERSION}</span>
        </div>

        <nav className={styles.col} aria-label="Footer navigation">
          <NavLink to="/" className={({ isActive }) => cn(styles.link, isActive && styles.linkActive)} end>
            Home
          </NavLink>
          {routes.filter((r) => r.showInNav).map((r) => (
            <NavLink
              key={r.path}
              to={r.path}
              className={({ isActive }) => cn(styles.link, isActive && styles.linkActive)}
            >
              {r.title}
            </NavLink>
          ))}
        </nav>

        <div className={styles.col}>
          <a
            href={GITHUB_REPO}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.ghLink}
          >
            <GitHubLogoIcon width={14} height={14} />
            <span>View on GitHub</span>
          </a>
          <span className={styles.license}>AGPL-3.0</span>
        </div>
      </div>
    </footer>
  );
}
