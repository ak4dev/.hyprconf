import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Tracks which section heading is currently in view based on scroll position.
 */
export function useScrollSpy(ids: string[]): string | null {
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    if (ids.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id);
          }
        }
      },
      {
        rootMargin: '-80px 0px -60% 0px',
        threshold: 0,
      }
    );

    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, [ids]);

  return activeId;
}

/**
 * Copy text to clipboard with success/error feedback and auto-reset.
 */
export function useCopyToClipboard(resetMs = 2000) {
  const [state, setState] = useState<'idle' | 'success' | 'error'>('idle');
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const copy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        setState('success');
      } catch {
        setState('error');
      }
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setState('idle'), resetMs);
    },
    [resetMs]
  );

  useEffect(() => {
    return () => clearTimeout(timerRef.current);
  }, []);

  return { copy, state };
}

/**
 * Responsive breakpoint detection.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener('change', handler);
    setMatches(mql.matches);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}
