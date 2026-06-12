"use client";

type TablePagerProps = {
  total: number;
  page: number;
  pageCount: number;
  pageSize: number;
  startIndex: number;
  endIndex: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
};

export default function TablePager({
  total,
  page,
  pageCount,
  pageSize,
  startIndex,
  endIndex,
  onPageChange,
  onPageSizeChange,
}: TablePagerProps) {
  const show = total > 5;

  return (
    <nav
      className="table-pager"
      data-pager
      hidden={!show}
      aria-label="Result pages"
    >
      <div className="table-pager__info" data-pager-info>
        {total === 0
          ? "0 results"
          : `Showing ${startIndex + 1}–${endIndex} of ${total}`}
      </div>
      <div className="table-pager__controls" role="group" aria-label="Page navigation">
        <button
          type="button"
          className="btn btn--ghost table-pager__btn"
          data-pager-first
          aria-label="First page"
          title="First page"
          disabled={page <= 1}
          onClick={() => onPageChange(1)}
        >
          «
        </button>
        <button
          type="button"
          className="btn btn--ghost table-pager__btn"
          data-pager-prev
          aria-label="Previous page"
          title="Previous page"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <span aria-hidden="true">‹</span>
          <span className="table-pager__btn-label"> Prev</span>
        </button>
        <span className="table-pager__page" data-pager-page aria-live="polite">
          Page {page} / {pageCount}
        </span>
        <button
          type="button"
          className="btn btn--ghost table-pager__btn"
          data-pager-next
          aria-label="Next page"
          title="Next page"
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          <span className="table-pager__btn-label">Next </span>
          <span aria-hidden="true">›</span>
        </button>
        <button
          type="button"
          className="btn btn--ghost table-pager__btn"
          data-pager-last
          aria-label="Last page"
          title="Last page"
          disabled={page >= pageCount}
          onClick={() => onPageChange(pageCount)}
        >
          »
        </button>
      </div>
      <label className="table-pager__size">
        <span className="table-pager__size-label">Per page</span>
        <select
          className="input table-pager__size-select"
          data-pager-size
          value={String(pageSize)}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
        >
          <option value="5">5</option>
          <option value="10">10</option>
          <option value="25">25</option>
          <option value="50">50</option>
          <option value="100">100</option>
          <option value="0">All</option>
        </select>
      </label>
    </nav>
  );
}
