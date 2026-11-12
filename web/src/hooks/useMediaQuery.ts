import { useEffect, useState } from "react";

/** Tailwind `lg` breakpoint: 1024px. */
export const DESKTOP_MEDIA = "(min-width: 1024px)";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = () => setMatches(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

export function useIsDesktop(): boolean {
  return useMediaQuery(DESKTOP_MEDIA);
}

/** Home path after login / onboarding. */
export function deckHomePath(_isDesktop: boolean): string {
  return "/deck";
}
