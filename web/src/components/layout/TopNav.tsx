import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { GitHubLogoIcon } from '@radix-ui/react-icons';
import { routes } from '@/routes';
import { GITHUB_REPO } from '@/content';
import { ThemePicker } from '@/components/ThemePicker';
import { useMediaQuery } from '@/lib/hooks';
import { cn } from '@/lib/cn';
import styles from './TopNav.module.css';

export function TopNav() {
  const isMobile = useMediaQuery('(max-width: 767px)');
  const [menuOpen, setMenuOpen] = useState(false);

  const navLinks = routes.filter((r) => r.showInNav);

  return (
    <header className={styles.nav}>
      <div className={styles.inner}>
        <NavLink to="/" className={styles.logo} aria-label="hyprconf home">
          hyprconf<span className={styles.dot}>.</span>
        </NavLink>

        {!isMobile && (
          <nav className={styles.links} aria-label="Main navigation">
            {navLinks.map((r) => (
              <NavLink
                key={r.path}
                to={r.path}
                className={({ isActive }) => cn(styles.link, isActive && styles.linkActive)}
              >
                {r.title}
              </NavLink>
            ))}
          </nav>
        )}

        <div className={styles.actions}>
          <a
            href={GITHUB_REPO}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.iconLink}
            aria-label="GitHub repository"
          >
            <GitHubLogoIcon width={18} height={18} />
          </a>
          <ThemePicker />
          {isMobile && (
            <button
              type="button"
              className={styles.hamburger}
              onClick={() => setMenuOpen(!menuOpen)}
              aria-expanded={menuOpen}
              aria-label="Toggle navigation"
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          )}
        </div>
      </div>

      {isMobile && menuOpen && (
        <nav className={styles.mobileMenu} aria-label="Mobile navigation">
          {navLinks.map((r) => (
            <NavLink
              key={r.path}
              to={r.path}
              className={({ isActive }) => cn(styles.mobileLink, isActive && styles.linkActive)}
              onClick={() => setMenuOpen(false)}
            >
              {r.title}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}
