"use client";

import { useEffect } from "react";
import { reportError } from "@/lib/telemetry/errors";

type ErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    reportError(error, {
      source: "route.error_boundary",
      digest: error.digest,
    });
  }, [error]);

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Something went wrong</h1>
        <p className="muted">This page hit an unexpected error.</p>
        <button type="button" className="btn btn-primary" onClick={reset}>
          Try again
        </button>
      </section>
    </main>
  );
}
