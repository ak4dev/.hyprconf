import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Copy text to clipboard with success/error feedback and auto-reset.
 */
export function useCopyToClipboard(resetMs = 2000) {
  const [state, setState] = useState<'idle' | 'success' | 'error'>('idle');
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

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
