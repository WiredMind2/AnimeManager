import Link from "next/link";

type FilterOption = {
  value: string;
  label: string;
  dot?: string | null;
};

export function FilterChips({
  options,
  activeFilter,
  query,
}: {
  options: FilterOption[];
  activeFilter: string;
  query?: string;
}) {
  const active = (activeFilter || "DEFAULT").toUpperCase();
  const q = (query || "").trim();

  return (
    <div className="chip-row" role="tablist" aria-label="Filters">
      {options.map((option) => {
        const value = (option.value || "DEFAULT").toUpperCase();
        const isActive = value === active;
        const href = `/library?filter=${encodeURIComponent(option.value)}${
          q ? `&q=${encodeURIComponent(q)}` : ""
        }`;
        return (
          <Link
            key={option.value}
            href={href}
            className={`chip ${isActive ? "is-active" : ""}`}
            role="tab"
            aria-selected={isActive}
          >
            {option.dot ? (
              <span className="chip__dot" style={{ background: option.dot }} />
            ) : null}
            {option.label}
          </Link>
        );
      })}
    </div>
  );
}
