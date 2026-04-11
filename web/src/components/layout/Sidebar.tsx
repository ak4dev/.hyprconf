import { useScrollSpy } from '@/lib/hooks';
import { cn } from '@/lib/cn';
import styles from './Sidebar.module.css';

interface SidebarSection {
  id: string;
  title: string;
}

interface SidebarProps {
  sections: SidebarSection[];
}

export function Sidebar({ sections }: SidebarProps) {
  const ids = sections.map((s) => s.id);
  const activeId = useScrollSpy(ids);

  return (
    <aside className={styles.sidebar} aria-label="Page sections">
      <nav className={styles.nav}>
        {sections.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            className={cn(styles.link, activeId === s.id && styles.linkActive)}
            aria-current={activeId === s.id ? 'true' : undefined}
          >
            {s.title}
          </a>
        ))}
      </nav>
    </aside>
  );
}
