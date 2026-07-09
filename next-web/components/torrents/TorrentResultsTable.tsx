"use client";

import { useCallback, useMemo, useState } from "react";
import type { TorrentTableRow } from "@/lib/api";
import { isAdultTorrent } from "@/lib/adultContent";
import TorrentFiltersBar, {
  EMPTY_FILTERS,
  type TorrentFilterState,
} from "./TorrentFiltersBar";
import TorrentRow from "./TorrentRow";
import TablePager from "./TablePager";

type SortState = { key: string; dir: "asc" | "desc"; type: "text" | "number" } | null;

type TorrentResultsTableProps = {
  rows: TorrentTableRow[];
  animeId?: number;
  streamMode?: boolean;
  hideNsfw?: boolean;
};

function rowMatchesFilters(row: TorrentTableRow, filters: TorrentFilterState): boolean {
  const f = row.filter;
  if (filters.pub && f.pub !== filters.pub) return false;
  if (filters.res && f.res !== filters.res) return false;
  if (filters.codec && f.codec !== filters.codec) return false;
  if (filters.source && f.source !== filters.source) return false;
  if (filters.provider && f.provider !== filters.provider) return false;
  if (filters.season && f.season !== filters.season) return false;
  if (filters.episodeKind && (f["episode-kind"] || "none") !== filters.episodeKind) return false;

  const minRaw = filters.episodeMin.trim();
  const maxRaw = filters.episodeMax.trim();
  if (minRaw || maxRaw) {
    if (!row.epStart || !row.epEnd) return false;
    const start = Number(row.epStart);
    const end = Number(row.epEnd);
    const min = minRaw ? Number(minRaw) : -Infinity;
    const max = maxRaw ? Number(maxRaw) : Infinity;
    if (Number.isNaN(start) || Number.isNaN(end)) return false;
    if (end < min || start > max) return false;
  }
  return true;
}

function harvestOptions(rows: TorrentTableRow[]): Record<string, string[]> {
  const sets: Record<string, Set<string>> = {
    pub: new Set(),
    res: new Set(),
    codec: new Set(),
    source: new Set(),
    provider: new Set(),
    season: new Set(),
  };
  for (const row of rows) {
    for (const [k, v] of Object.entries(row.filter)) {
      if (sets[k] && v) sets[k].add(v);
    }
  }
  const out: Record<string, string[]> = {};
  for (const [k, set] of Object.entries(sets)) {
    out[k] = Array.from(set).sort((a, b) =>
      a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }),
    );
  }
  return out;
}

export default function TorrentResultsTable({
  rows,
  animeId,
  streamMode = false,
  hideNsfw = true,
}: TorrentResultsTableProps) {
  const [filters, setFilters] = useState<TorrentFilterState>(EMPTY_FILTERS);
  const [sort, setSort] = useState<SortState>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);

  const options = useMemo(() => harvestOptions(rows), [rows]);

  const filtered = useMemo(
    () =>
      rows.filter((r) => {
        if (hideNsfw && isAdultTorrent(r.name)) return false;
        return rowMatchesFilters(r, filters);
      }),
    [rows, filters, hideNsfw],
  );

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const { key, dir, type } = sort;
    const copy = [...filtered];
    copy.sort((a, b) => {
      const va = (a.sort as Record<string, string | number>)[key];
      const vb = (b.sort as Record<string, string | number>)[key];
      let cmp: number;
      if (type === "number") {
        cmp = Number(va) - Number(vb);
      } else {
        cmp = String(va).localeCompare(String(vb), undefined, {
          numeric: true,
          sensitivity: "base",
        });
      }
      if (cmp === 0) return 0;
      return dir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [filtered, sort]);

  const pageCount = pageSize === 0 ? 1 : Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(Math.max(1, page), pageCount);
  const startIndex = pageSize === 0 ? 0 : (safePage - 1) * pageSize;
  const endIndex = pageSize === 0 ? sorted.length : Math.min(sorted.length, safePage * pageSize);

  const paged = useMemo(() => {
    if (pageSize === 0) return sorted;
    const start = (safePage - 1) * pageSize;
    return sorted.slice(start, start + pageSize);
  }, [sorted, safePage, pageSize]);

  const toggleSort = useCallback(
    (key: string, type: "text" | "number", defaultDir: "asc" | "desc" = "asc") => {
      setSort((prev) => {
        if (!prev || prev.key !== key) return { key, dir: defaultDir, type };
        if (prev.dir === "asc") return { key, dir: "desc", type };
        return null;
      });
      setPage(1);
    },
    [],
  );

  const onFilterClick = useCallback((facet: string, value: string) => {
    setFilters((prev) => {
      const map: Record<string, keyof TorrentFilterState> = {
        pub: "pub",
        res: "res",
        codec: "codec",
        source: "source",
        provider: "provider",
        season: "season",
        "episode-kind": "episodeKind",
      };
      const field = map[facet];
      if (!field) return prev;
      const current = prev[field];
      return { ...prev, [field]: current === value ? "" : value };
    });
    setPage(1);
  }, []);

  const resetFilters = useCallback(() => {
    setFilters(EMPTY_FILTERS);
    setPage(1);
  }, []);

  const sortClass = (key: string) => {
    if (!sort || sort.key !== key) return "is-sortable";
    return `is-sortable is-sorted is-sorted-${sort.dir}`;
  };

  const sortAria = (key: string) => {
    if (!sort || sort.key !== key) return undefined;
    return sort.dir === "asc" ? "ascending" : "descending";
  };

  return (
    <>
      <TorrentFiltersBar
        filters={filters}
        options={options}
        onChange={(next) => {
          setFilters(next);
          setPage(1);
        }}
        onReset={resetFilters}
      />
      <div className="table-pager-wrap" data-paginate-wrap>
        <div className="table-wrap table-wrap--scroll">
          <table className="table table--torrents" data-sortable>
            <colgroup>
              <col className="col--release" />
              <col className="col--publisher" />
              <col className="col--quality" />
              <col className="col--codec" />
              <col className="col--source" />
              <col className="col--season" />
              <col className="col--episode" />
              <col className="col--size" />
              <col className="col--seeds" />
              <col className="col--leech" />
              <col className="col--actions" />
            </colgroup>
            <thead>
              <tr>
                <th
                  className={sortClass("name")}
                  data-sort="name"
                  data-sort-type="text"
                  aria-sort={sortAria("name")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("name", "text")}
                >
                  Release
                </th>
                <th
                  className={sortClass("pub")}
                  data-sort="pub"
                  data-sort-type="text"
                  aria-sort={sortAria("pub")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("pub", "text")}
                >
                  Publisher
                </th>
                <th
                  className={`num ${sortClass("res")}`}
                  data-sort="res"
                  data-sort-type="number"
                  aria-sort={sortAria("res")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("res", "number")}
                >
                  Quality
                </th>
                <th
                  className={sortClass("codec")}
                  data-sort="codec"
                  data-sort-type="text"
                  aria-sort={sortAria("codec")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("codec", "text")}
                >
                  Codec
                </th>
                <th
                  className={sortClass("source")}
                  data-sort="source"
                  data-sort-type="text"
                  aria-sort={sortAria("source")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("source", "text")}
                >
                  Source
                </th>
                <th
                  className={`num ${sortClass("season")}`}
                  data-sort="season"
                  data-sort-type="number"
                  aria-sort={sortAria("season")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("season", "number")}
                >
                  S
                </th>
                <th
                  className={`num ${sortClass("episode")}`}
                  data-sort="episode"
                  data-sort-type="number"
                  aria-sort={sortAria("episode")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("episode", "number")}
                >
                  Ep
                </th>
                <th
                  className={`num ${sortClass("size")}`}
                  data-sort="size"
                  data-sort-type="number"
                  aria-sort={sortAria("size")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("size", "number")}
                >
                  Size
                </th>
                <th
                  className={`num ${sortClass("seeds")}`}
                  data-sort="seeds"
                  data-sort-type="number"
                  data-sort-default="desc"
                  aria-sort={sortAria("seeds")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("seeds", "number", "desc")}
                >
                  Seeds
                </th>
                <th
                  className={`num ${sortClass("leech")}`}
                  data-sort="leech"
                  data-sort-type="number"
                  aria-sort={sortAria("leech")}
                  role="columnheader"
                  tabIndex={0}
                  onClick={() => toggleSort("leech", "number")}
                >
                  Leech
                </th>
                <th />
              </tr>
            </thead>
            <tbody data-stream-rows={streamMode ? "" : undefined} data-paginate>
              {paged.map((row) => (
                <TorrentRow
                  key={row.id}
                  row={row}
                  animeId={animeId}
                  onFilterClick={onFilterClick}
                />
              ))}
            </tbody>
          </table>
        </div>
        <TablePager
          total={sorted.length}
          page={safePage}
          pageCount={pageCount}
          pageSize={pageSize}
          startIndex={startIndex}
          endIndex={endIndex}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      </div>
      <p
        className="anime-torrent-empty"
        data-stream-filter-empty
        style={{
          display: rows.length > 0 && filtered.length === 0 ? "" : "none",
          color: "var(--text-faint)",
          fontSize: 13,
          marginTop: "var(--sp-4)",
        }}
      >
        No releases match the current filters.
        <button
          type="button"
          className="btn btn--ghost btn--small"
          data-torrent-filter-reset
          onClick={resetFilters}
        >
          Reset filters
        </button>
      </p>
    </>
  );
}
