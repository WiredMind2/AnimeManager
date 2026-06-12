import { FILTER_OPTIONS } from "@/lib/config";

type FilterChipsProps = {
  activeFilter: string;
  q?: string | null;
};

function chipHref(filterValue: string, q?: string | null): string {
  const params = new URLSearchParams();
  params.set("filter", filterValue);
  if (q) params.set("q", q);
  return `/library?${params.toString()}`;
}

export default function FilterChips({ activeFilter, q }: FilterChipsProps) {
  const normalizedActive = (activeFilter || "DEFAULT").toUpperCase();

  return (
    <div className="chip-row" role="tablist" aria-label="Filters">
      {FILTER_OPTIONS.map((option) => {
        const isActive = (option.value || "DEFAULT").toUpperCase() === normalizedActive;
        return (
          <a
            key={option.value}
            className={`chip${isActive ? " is-active" : ""}`}
            href={chipHref(option.value, q)}
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
    </div>
  );
}
