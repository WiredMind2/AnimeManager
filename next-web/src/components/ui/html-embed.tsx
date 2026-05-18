"use client";

import { useEffect, useRef } from "react";

/** Inject server-rendered HTML and re-run legacy ``app.js`` hooks. */
export function HtmlEmbed({ html, className }: { html: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const target = ref.current;
    if (!target) return;
    target.dispatchEvent(
      new CustomEvent("htmx:afterSwap", { detail: { target }, bubbles: true }),
    );
  }, [html]);

  return (
    <div
      ref={ref}
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
