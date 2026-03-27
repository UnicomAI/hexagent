/**
 * Shared hook for loading favicons with cascading fallback.
 *
 * Strategy:
 *   1. Fire root /favicon.ico, Google, and DuckDuckGo probes in parallel
 *   2. First success wins → resolved URL
 *   3. After FAST_TIMEOUT_MS with no success → signal fallback (caller shows letter)
 *   4. Keep trying in background — if a late probe succeeds, swap in the URL
 *   5. After GIVE_UP_MS → stop trying permanently
 */

import { useState, useEffect, useRef } from "react";

/** Show letter fallback after this many ms with no success. */
const FAST_TIMEOUT_MS = 2000;
/** Stop trying entirely after this many ms. */
const GIVE_UP_MS = 8000;

interface FaviconState {
  /** Resolved favicon URL, or null if not yet loaded / failed. */
  src: string | null;
  /** True when we've passed the fast timeout without success (show letter). */
  showFallback: boolean;
}

/**
 * Probe an image URL. Resolves with the URL on success, rejects on error.
 */
function probeImage(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(url);
    img.onerror = () => reject();
    img.src = url;
  });
}

/**
 * Hook to load a favicon with cascading fallback.
 *
 * @param domain - The domain to load a favicon for (e.g. "example.com").
 *                 Pass undefined/empty to skip loading.
 * @param siteUrl - Optional full URL to derive the root /favicon.ico from.
 */
export function useFavicon(domain: string | undefined, siteUrl?: string): FaviconState {
  const [src, setSrc] = useState<string | null>(null);
  const [showFallback, setShowFallback] = useState(false);
  // Track the domain we're loading for, to reset on change
  const activeDomain = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!domain) {
      setSrc(null);
      setShowFallback(false);
      return;
    }

    // Reset when domain changes
    if (domain !== activeDomain.current) {
      activeDomain.current = domain;
      setSrc(null);
      setShowFallback(false);
    }

    let cancelled = false;
    let resolved = false;

    // Build probe URLs
    const probes: string[] = [];

    if (siteUrl) {
      try {
        probes.push(new URL(siteUrl).origin + "/favicon.ico");
      } catch {
        // invalid URL
      }
    }

    probes.push(
      `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`,
      `https://icons.duckduckgo.com/ip3/${encodeURIComponent(domain)}.ico`,
    );

    // Fast timeout: show letter fallback if nothing resolved yet
    const fastTimer = setTimeout(() => {
      if (!cancelled && !resolved) setShowFallback(true);
    }, FAST_TIMEOUT_MS);

    // Give-up timeout: stop trying
    const giveUpTimer = setTimeout(() => {
      cancelled = true;
    }, GIVE_UP_MS);

    // Fire all probes in parallel — first success wins
    let failures = 0;
    for (const url of probes) {
      probeImage(url).then(
        (resolvedUrl) => {
          if (!cancelled && !resolved) {
            resolved = true;
            setSrc(resolvedUrl);
            setShowFallback(false);
          }
        },
        () => {
          failures++;
          if (failures === probes.length && !cancelled && !resolved) {
            // All probes failed — show fallback immediately
            setShowFallback(true);
          }
        },
      );
    }

    return () => {
      cancelled = true;
      clearTimeout(fastTimer);
      clearTimeout(giveUpTimer);
    };
  }, [domain, siteUrl]);

  return { src, showFallback };
}
