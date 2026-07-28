import type { DownloadsOverview } from "@/lib/api";

/** Fold ``other`` bucket rows into ``active`` so unknown states stay visible. */
export function mergeOverviewOtherIntoActive(
  overview: DownloadsOverview,
): DownloadsOverview {
  const other = overview.other ?? [];
  if (!other.length) {
    return overview;
  }
  return {
    ...overview,
    active: [...(overview.active ?? []), ...other],
    other: [],
  };
}
