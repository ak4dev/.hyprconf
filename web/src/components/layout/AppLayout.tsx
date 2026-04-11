import { Suspense } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { TopNav } from './TopNav';
import { Sidebar } from './Sidebar';
import { Footer } from './Footer';
import { ErrorBoundary } from './ErrorBoundary';
import { PageSkeleton } from '@/components/PageSkeleton';
import { routes } from '@/routes';
import { useMediaQuery } from '@/lib/hooks';
import { cn } from '@/lib/cn';
import styles from './AppLayout.module.css';

export function AppLayout() {
  const location = useLocation();
  const isMobile = useMediaQuery('(max-width: 767px)');

  const currentRoute = routes.find((r) => r.path === location.pathname);
  const showSidebar = !isMobile && !!currentRoute?.hasSidebar;

  return (
    <div className={styles.layout}>
      <TopNav />
      <div className={cn(styles.body, showSidebar && styles.withSidebar)}>
        {showSidebar && <Sidebar sections={[]} />}
        <main className={styles.main}>
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      <Footer />
    </div>
  );
}
