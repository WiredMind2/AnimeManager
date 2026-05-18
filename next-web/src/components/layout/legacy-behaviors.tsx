"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

/** Re-run legacy ``app.js`` wiring after Next.js client navigations. */
export function LegacyBehaviors() {
  const pathname = usePathname();

  useEffect(() => {
    const target = document;
    target.dispatchEvent(
      new CustomEvent("htmx:afterSwap", { detail: { target }, bubbles: true }),
    );
  }, [pathname]);

  return null;
}
