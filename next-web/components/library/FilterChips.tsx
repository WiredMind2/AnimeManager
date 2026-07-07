import { FILTER_OPTIONS, type FilterValue } from "@/lib/config";
import { libraryPageUrl, type PageSizeOption } from "@/lib/library";
import SeasonBrowseChip from "./SeasonBrowseChip";

type FilterChipsProps = {
  activeFilter: string;
  q?: string | null;
  pageSize: PageSizeOption;
  hideRated: boolean;
  settingsHideRated: boolean;
  settingsPageSize: PageSizeOption;
};

function chipHref(
  filterValue: FilterValue,
  q: string | null | undefined,
  pageSize: PageSizeOption,
  hideRated: boolean,
  settingsHideRated: boolean,
  settingsPageSize: PageSizeOption,
): string {
  return libraryPageUrl({
    filter: filterValue,
    q: q ?? undefined,
    size: pageSize,
    hideRated,
    settingsHideRated,
    settingsPageSize,
  });
}

export default function FilterChips({
  activeFilter,
  q,
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
          <a
            key={option.value}
            className={`chip${isActive ? " is-active" : ""}`}
            href={chipHref(
              option.value,
              q,
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
          </a>
        );
      })}
      <SeasonBrowseChip />
    </div>
  );
}
