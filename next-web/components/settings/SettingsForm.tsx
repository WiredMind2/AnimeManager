"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import SettingsField from "./SettingsField";
import SettingsToc from "./SettingsToc";
import FileBrowserModal from "./FileBrowserModal";
import type { SectionNode } from "@/lib/settings-form";
import { saveSettingsFromForm } from "@/lib/settings-save";

type SettingsFormProps = {
  sections: SectionNode[];
  currentSettings: Record<string, unknown>;
  currentSettingsJson: string;
  logCategories?: string[];
};

type Flash = {
  kind: "success" | "error" | "info";
  message: string;
};

function syncColorPickers(form: HTMLFormElement): void {
  form.querySelectorAll<HTMLInputElement>("input[type='color']").forEach((picker) => {
    const name = picker.name;
    if (!name) return;
    const mirror = form.querySelector<HTMLInputElement>(`#t-${CSS.escape(name)}`);
    if (!mirror) return;
    const raw = mirror.value.trim();
    if (/^#[0-9a-fA-F]{6}$/.test(raw)) {
      picker.value = raw;
    }
  });
}

export default function SettingsForm({
  sections,
  currentSettings,
  currentSettingsJson,
  logCategories = [],
}: SettingsFormProps) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(sections.map((s) => [s.name, s.open_by_default])),
  );
  const [flash, setFlash] = useState<Flash | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [rawSettingsJson, setRawSettingsJson] = useState("");
  const [browseTarget, setBrowseTarget] = useState<{
    inputId: string;
    path: string;
  } | null>(null);

  const handleExpandAll = useCallback(
    (mode: "all" | "none") => {
      setOpenSections(Object.fromEntries(sections.map((s) => [s.name, mode === "all"])));
    },
    [sections],
  );

  useEffect(() => {
    const openHashTarget = () => {
      const id = window.location.hash.slice(1);
      if (!id || !id.startsWith("section-")) return;
      const sectionName = id.replace(/^section-/, "");
      setOpenSections((prev) => ({ ...prev, [sectionName]: true }));
      window.requestAnimationFrame(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    };

    openHashTarget();
    window.addEventListener("hashchange", openHashTarget);
    return () => window.removeEventListener("hashchange", openHashTarget);
  }, []);

  const handleBrowsePath = useCallback((inputId: string, currentValue: string) => {
    setBrowseTarget({ inputId, path: currentValue });
  }, []);

  const handleBrowseSelect = useCallback((inputId: string, path: string) => {
    const input = document.getElementById(inputId) as HTMLInputElement | null;
    if (input) {
      input.value = path;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }, []);

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const form = formRef.current;
      if (!form) return;

      setSaving(true);
      setFlash(null);
      setValidationError(null);

      syncColorPickers(form);

      const formData = new FormData(form);
      if (rawSettingsJson.trim()) {
        formData.set("settings_json", rawSettingsJson.trim());
      }

      try {
        const { result } = await saveSettingsFromForm(formData, currentSettings, {
          logCategories,
        });

        if (result.ok) {
          setFlash({
            kind: result.kind ?? "success",
            message: result.message ?? "Settings saved.",
          });
          if (!rawSettingsJson.trim()) {
            setRawSettingsJson("");
          }
          router.refresh();
        } else {
          setValidationError(result.message ?? "Could not save settings.");
        }
      } catch (err) {
        setValidationError(
          err instanceof Error ? err.message : "Could not save settings.",
        );
      } finally {
        setSaving(false);
      }
    },
    [currentSettings, logCategories, rawSettingsJson, router],
  );

  const handleReset = useCallback(() => {
    setFlash(null);
    setValidationError(null);
    setRawSettingsJson("");
    router.refresh();
  }, [router]);

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="page-head__title">Settings</h1>
          <p className="page-head__subtitle">
            Fields below are rendered from the active{" "}
            <code style={{ fontFamily: "var(--font-mono)", color: "var(--accent)" }}>
              settings.json
            </code>{" "}
            and saved through{" "}
            <code style={{ fontFamily: "var(--font-mono)", color: "var(--accent)" }}>
              update_settings
            </code>
            . Sections are ordered by typical importance; less-used ones are collapsed by
            default. Use the advanced editor at the bottom to add or remove keys.
          </p>
        </div>
        <SettingsToc sections={sections} onExpandAll={handleExpandAll} />
      </header>

      {validationError ? (
        <div className="flash flash--error">{validationError}</div>
      ) : null}
      {flash ? <div className={`flash flash--${flash.kind}`}>{flash.message}</div> : null}

      <form
        ref={formRef}
        className="settings-form"
        id="settings-form"
        onSubmit={handleSubmit}
      >
        {sections.map((section) => (
          <details
            key={section.name}
            id={`section-${section.name}`}
            className={`settings-section settings-section--tier-${section.tier}${
              section.is_bool_only ? " settings-section--toggles" : ""
            }`}
            data-settings-section
            open={openSections[section.name]}
            onToggle={(e) => {
              const target = e.currentTarget;
              setOpenSections((prev) => ({
                ...prev,
                [section.name]: target.open,
              }));
            }}
          >
            <summary className="settings-section__head">
              <div className="settings-section__head-text">
                <h2 className="settings-section__title">{section.section_label}</h2>
                {section.description ? (
                  <p className="settings-section__description">{section.description}</p>
                ) : null}
              </div>
              <div className="settings-section__head-meta">
                {section.tier === 3 ? <span className="badge">Legacy</span> : null}
                {section.tier === 2 ? <span className="badge">Optional</span> : null}
                <code className="settings-section__path">settings.{section.name}</code>
              </div>
            </summary>
            <div className="settings-section__body">
              {section.children.length ? (
                section.children.map((child) => (
                  <SettingsField
                    key={child.name}
                    node={child}
                    onBrowsePath={handleBrowsePath}
                  />
                ))
              ) : (
                <p className="settings-field__hint">
                  Empty section — use the advanced editor below to populate it.
                </p>
              )}
            </div>
          </details>
        ))}

        <details className="settings-advanced">
          <summary className="settings-advanced__summary">
            Advanced — edit raw <code>settings.json</code>
          </summary>
          <div className="settings-advanced__body">
            <p className="settings-field__hint">
              Anything pasted here is merged on save and takes precedence over the fields
              above. Leave empty to only apply the structured fields.
            </p>
            <textarea
              className="textarea"
              name="settings_json"
              spellCheck={false}
              placeholder='{ "ui": { "theme": "dark" } }'
              value={rawSettingsJson}
              onChange={(e) => setRawSettingsJson(e.target.value)}
            />
            <details className="settings-advanced__current">
              <summary>Show current settings.json</summary>
              <pre className="settings-advanced__pre">{currentSettingsJson}</pre>
            </details>
          </div>
        </details>

        <div className="settings-form__actions">
          <button type="button" className="btn btn--ghost" onClick={handleReset}>
            Reset
          </button>
          <button className="btn btn--primary" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>

      <FileBrowserModal
        open={browseTarget !== null}
        targetInputId={browseTarget?.inputId ?? null}
        initialPath={browseTarget?.path ?? ""}
        onClose={() => setBrowseTarget(null)}
        onSelect={handleBrowseSelect}
      />
    </>
  );
}
