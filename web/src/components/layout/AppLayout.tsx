import { Suspense } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { TopNav } from './TopNav';
import { Footer } from './Footer';
import { ErrorBoundary } from './ErrorBoundary';
import { PageSkeleton } from '@/components/PageSkeleton';
import styles from './AppLayout.module.css';

export function AppLayout() {
  const location = useLocation();

  return (
    <div className={styles.layout}>
      <TopNav />
      <div className={styles.body}>
        <main className={styles.main}>
          <ErrorBoundary key={location.pathname}>
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
