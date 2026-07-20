import Link from "next/link";

type BrowsePagerProps = {
  listStart: number;
  itemCount: number;
  prevUrl: string | null;
  nextUrl: string | null;
  filterLabel?: string;
};

export default function BrowsePager({
  listStart,
  itemCount,
  prevUrl,
  nextUrl,
  filterLabel,
}: BrowsePagerProps) {
  if (itemCount <= 0 && !prevUrl && !nextUrl) {
    return filterLabel ? (
      <nav className="pager pager--empty" aria-label="Browse status">
        <span className="pager__filter-label">{filterLabel}</span>
      </nav>
    ) : null;
  }

  return (
    <nav className="pager" aria-label="Pagination">
      <span>
        {itemCount > 0 ? (
          <>
            Showing <strong>{listStart + 1}</strong>–
            <strong>{listStart + itemCount}</strong>
          </>
        ) : (
          "No results on this page"
        )}
      </span>
      <div className="pager__actions">
        {prevUrl ? (
          <Link className="btn" href={prevUrl}>
            ← Previous
          </Link>
        ) : (
          <span className="btn" aria-disabled="true">
            ← Previous
          </span>
        )}
        {nextUrl ? (
          <Link className="btn" href={nextUrl}>
            Next →
          </Link>
        ) : (
          <span className="btn" aria-disabled="true">
            Next →
          </span>
        )}
      </div>
      {filterLabel ? <span className="pager__filter-label">{filterLabel}</span> : null}
    </nav>
  );
}
