"use client";

import { useEffect, useState, type RefObject } from "react";
import {
  neededCoverPx,
  pickCoverUrl,
  type CoverVariant,
} from "./pick-cover-url";

/**
 * Measure a poster slot and pick the smallest cover that still covers it
 * (CSS width × devicePixelRatio). Falls back to ``fallback`` until measured.
 */
export function useCoverSrc(
  slotRef: RefObject<HTMLElement | null>,
  variants: CoverVariant[] | null | undefined,
  fallback?: string | null,
): string | null {
  const [src, setSrc] = useState<string | null>(() =>
    pickCoverUrl(variants, 0, fallback) || (fallback ?? null),
  );

  useEffect(() => {
    const el = slotRef.current;
    if (!el || typeof ResizeObserver === "undefined") {
      setSrc(pickCoverUrl(variants, 0, fallback) || fallback || null);
      return;
    }

    const update = () => {
      const cssWidth = el.getBoundingClientRect().width;
      const dpr =
        typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
      const needed = neededCoverPx(cssWidth, dpr);
      setSrc(pickCoverUrl(variants, needed, fallback) || fallback || null);
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);

    const onDprChange = () => update();
    window.addEventListener("resize", onDprChange);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", onDprChange);
    };
  }, [slotRef, variants, fallback]);

  return src;
}
