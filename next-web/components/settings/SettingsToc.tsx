"use client";

import type { SectionNode } from "@/lib/settings-form";

type SettingsTocProps = {
  sections: SectionNode[];
  onExpandAll: (mode: "all" | "none") => void;
};

export default function SettingsToc({ sections, onExpandAll }: SettingsTocProps) {
  return (
    <nav className="settings-toc" aria-label="Sections">
      <div className="settings-toc__actions">
        <button
          type="button"
          className="chip"
          onClick={() => onExpandAll("all")}
        >
          Expand all
        </button>
        <button
          type="button"
          className="chip"
          onClick={() => onExpandAll("none")}
        >
          Collapse all
        </button>
      </div>
      <div className="settings-toc__links">
        {sections.map((section) => (
          <a
            key={section.name}
            className={`chip settings-toc__chip settings-toc__chip--tier-${section.tier}`}
            href={`#section-${section.name}`}
            data-tier={section.tier}
          >
            {section.section_label}
          </a>
        ))}
      </div>
    </nav>
  );
}
