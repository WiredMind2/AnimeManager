"use client";

import { useEffect } from "react";
import { reportError } from "@/lib/telemetry/errors";

type GlobalErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalErrorPage({ error, reset }: GlobalErrorPageProps) {
  useEffect(() => {
    reportError(error, {
      source: "global.error_boundary",
      digest: error.digest,
    });
  }, [error]);

  return (
    <html lang="en">
      <body>
        <main style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
          <h1>Application error</h1>
          <p>The app encountered a fatal error.</p>
          <button type="button" onClick={reset}>
            Reload
          </button>
        </main>
      </body>
    </html>
  );
}
