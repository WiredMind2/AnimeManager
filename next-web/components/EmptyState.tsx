type EmptyStateProps = {
  icon?: string;
  title: string;
  hint?: string;
};

export default function EmptyState({ icon = "⌀", title, hint }: EmptyStateProps) {
  return (
    <div className="state">
      <div className="state__icon">{icon}</div>
      <div className="state__title">{title}</div>
      {hint ? <p className="state__hint">{hint}</p> : null}
    </div>
  );
}
