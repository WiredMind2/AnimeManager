/**
 * Shared skeleton building blocks for route-level `loading.tsx` files.
 * Rendered instantly on client-side navigation while the server component
 * for the target route is still fetching.
 */

export function PageHeadSkeleton() {
  return (
    <header className="page-head" aria-hidden="true">
      <div style={{ flex: 1, minWidth: 0 }}>
        <span
          className="skeleton-line"
          style={{ display: "block", height: 36, width: "40%", maxWidth: 320 }}
        />
        <span
          className="skeleton-line"
          style={{
            display: "block",
            width: "65%",
            maxWidth: 520,
            marginTop: "var(--sp-4)",
          }}
        />
      </div>
    </header>
  );
}

export function CardGridSkeleton({ count = 12 }: { count?: number }) {
  return (
    <section className="grid" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div className="card" key={i}>
          <div className="card__poster skeleton-block" />
          <span className="card__title-skeleton" />
        </div>
      ))}
    </section>
  );
}

export function DetailSkeleton() {
  return (
    <div className="detail detail--skeleton" aria-hidden="true">
      <div className="detail__skeleton-block detail__skeleton-block--poster" />
      <div className="detail__skeleton-body">
        <span className="detail__skeleton-line detail__skeleton-line--eyebrow" />
        <span className="detail__skeleton-line detail__skeleton-line--title" />
        <span className="detail__skeleton-line detail__skeleton-line--synopsis" />
        <span className="detail__skeleton-line detail__skeleton-line--synopsis" />
        <span className="detail__skeleton-line detail__skeleton-line--short" />
      </div>
    </div>
  );
}

export function PanelSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <section
      aria-hidden="true"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-4)",
        padding: "var(--sp-5)",
        borderRadius: "var(--r-2)",
        border: "1px solid var(--border)",
        background: "var(--surface-1)",
      }}
    >
      {Array.from({ length: rows }, (_, i) => (
        <span
          className="skeleton-line"
          key={i}
          style={{ width: `${88 - (i % 3) * 14}%` }}
        />
      ))}
    </section>
  );
}
