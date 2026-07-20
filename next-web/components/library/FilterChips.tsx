import Link from "next/link";
import { FILTER_OPTIONS, type FilterValue } from "@/lib/config";
import { libraryPageUrl, type PageSizeOption } from "@/lib/library";
import GenreBrowseChip from "./GenreBrowseChip";
import SeasonBrowseChip from "./SeasonBrowseChip";
import TopBrowseChip from "./TopBrowseChip";

type FilterChipsProps = {
  activeFilter: string;
  q?: string | null;
  backUrl?: string | null;
  pageSize: PageSizeOption;
  hideRated: boolean;
  settingsHideRated: boolean;
  settingsPageSize: PageSizeOption;
};

function chipHref(
  filterValue: FilterValue,
  q: string | null | undefined,
  backUrl: string | null | undefined,
  pageSize: PageSizeOption,
  hideRated: boolean,
  settingsHideRated: boolean,
  settingsPageSize: PageSizeOption,
): string {
  return libraryPageUrl({
    filter: filterValue,
    q: q ?? undefined,
    back: backUrl,
    size: pageSize,
    hideRated,
    settingsHideRated,
    settingsPageSize,
  });
}

export default function FilterChips({
  activeFilter,
  q,
  backUrl = null,
  pageSize,
  hideRated,
  settingsHideRated,
  settingsPageSize,
}: FilterChipsProps) {
  const normalizedActive = (activeFilter || "DEFAULT").toUpperCase();

  return (
    <div className="chip-row" role="tablist" aria-label="Filters">
      {FILTER_OPTIONS.map((option) => {
        const isActive = (option.value || "DEFAULT").toUpperCase() === normalizedActive;
        return (
          <Link
            key={option.value}
            className={`chip${isActive ? " is-active" : ""}`}
            href={chipHref(
              option.value,
              q,
              backUrl,
              pageSize,
              hideRated,
              settingsHideRated,
              settingsPageSize,
            )}
            role="tab"
            aria-selected={isActive ? "true" : "false"}
          >
            {option.dot ? (
              <span className="chip__dot" style={{ background: option.dot }} />
            ) : null}
            {option.label}
          </Link>
        );
      })}
      <SeasonBrowseChip />
      <GenreBrowseChip />
      <TopBrowseChip />
    </div>
  );
}
