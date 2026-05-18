export function EmptyState({
  icon = "∅",
  title = "Nothing here yet",
  hint = "",
}: {
  icon?: string;
  title?: string;
  hint?: string;
}) {
  return (
    <div className="state">
      <div className="state__icon">{icon}</div>
      <div className="state__title">{title}</div>
      {hint ? <p className="state__hint">{hint}</p> : null}
    </div>
  );
}
