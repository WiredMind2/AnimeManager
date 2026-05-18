"use client";

type SettingsNode = {
  kind: string;
  name?: string;
  label?: string;
  value?: unknown;
  children?: SettingsNode[];
  depth?: number;
  open_by_default?: boolean;
  section_label?: string;
  description?: string;
  options?: Array<{ value: string; label: string }>;
};

function SettingsNodeView({ node }: { node: SettingsNode }) {
  if (node.kind === "group") {
    return (
      <fieldset
        className={`settings-group settings-group--depth-${node.depth || 0}`}
      >
        {node.label ? <legend className="settings-group__legend">{node.label}</legend> : null}
        <div className="settings-group__children">
          {(node.children || []).map((child, idx) => (
            <SettingsNodeView key={`${child.name || child.label || "n"}-${idx}`} node={child} />
          ))}
        </div>
      </fieldset>
    );
  }

  if (node.kind === "bool") {
    return (
      <label className="settings-toggle">
        <input type="hidden" name="__bool__" value={node.name} />
        <input
          type="checkbox"
          className="settings-toggle__input"
          name={node.name}
          value="true"
          defaultChecked={Boolean(node.value)}
        />
        <span className="settings-toggle__label">{node.label}</span>
        {node.name ? <code className="settings-toggle__path">{node.name}</code> : null}
      </label>
    );
  }

  if (node.kind === "int" || node.kind === "float") {
    return (
      <label className="settings-field">
        <span className="settings-field__label">{node.label}</span>
        <input
          className="input settings-field__input"
          type="number"
          name={node.name}
          defaultValue={String(node.value ?? "")}
          step={node.kind === "float" ? "any" : "1"}
        />
        {node.name ? <code className="settings-field__path">{node.name}</code> : null}
      </label>
    );
  }

  if (node.kind === "select" && node.options?.length) {
    return (
      <label className="settings-field">
        <span className="settings-field__label">{node.label}</span>
        <select className="input settings-field__input" name={node.name} defaultValue={String(node.value ?? "")}>
          {node.options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {node.name ? <code className="settings-field__path">{node.name}</code> : null}
      </label>
    );
  }

  return (
    <label className="settings-field">
      <span className="settings-field__label">{node.label || node.name}</span>
      <input
        className="input settings-field__input"
        type="text"
        name={node.name}
        defaultValue={String(node.value ?? "")}
      />
      {node.name ? <code className="settings-field__path">{node.name}</code> : null}
    </label>
  );
}

export function SettingsForm({ sections }: { sections: SettingsNode[] }) {
  return (
    <form
      className="settings-form"
      method="post"
      action="/ui/settings"
      encType="multipart/form-data"
    >
      {sections.map((section, idx) => (
        <details
          key={`${section.section_label || "section"}-${idx}`}
          className="settings-section"
          id={`section-${section.name || idx}`}
          open={section.open_by_default}
        >
          <summary className="settings-section__summary">
            <span className="settings-section__title">{section.section_label}</span>
            {section.description ? (
              <span className="settings-section__desc">{section.description}</span>
            ) : null}
          </summary>
          <div className="settings-section__body">
            <SettingsNodeView node={section} />
          </div>
        </details>
      ))}

      <div className="settings-form__actions">
        <a className="btn btn--ghost" href="/settings">
          Reset
        </a>
        <button className="btn btn--primary" type="submit">
          Save changes
        </button>
      </div>
    </form>
  );
}
