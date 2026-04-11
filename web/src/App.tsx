import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@/lib/theme-provider';
import { AppLayout } from '@/components/layout/AppLayout';
import { routes } from '@/routes';
import { Suspense } from 'react';
import { ErrorBoundary } from '@/components/layout/ErrorBoundary';
import { PageSkeleton } from '@/components/PageSkeleton';
import Landing from '@/pages/Landing';
import NotFound from '@/pages/NotFound';

export function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Landing />} />
            {routes.map((r) => (
              <Route
                key={r.path}
                path={r.path}
                element={
                  <ErrorBoundary>
                    <Suspense fallback={<PageSkeleton />}>
                      <r.component />
                    </Suspense>
                  </ErrorBoundary>
                }
              />
            ))}
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </ThemeProvider>
    </BrowserRouter>
  );
}
