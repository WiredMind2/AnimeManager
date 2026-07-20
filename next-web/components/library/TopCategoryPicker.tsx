"use client";

import { TOP_CATEGORY_SPECS, type TopCategory } from "@/lib/top";

type TopCategoryPickerProps = {
  value: TopCategory;
  onChange: (next: TopCategory) => void;
};

export default function TopCategoryPicker({ value, onChange }: TopCategoryPickerProps) {
  return (
    <div className="season-picker top-picker">
      <div className="season-tabs" role="tablist" aria-label="Top category">
        {TOP_CATEGORY_SPECS.map((spec) => (
          <button
            key={spec.key}
            type="button"
            role="tab"
            aria-selected={spec.key === value}
            data-top-category={spec.key}
            className={`season-tab${spec.key === value ? " is-active" : ""}`}
            onClick={() => {
              if (spec.key !== value) onChange(spec.key);
            }}
          >
            <span>{spec.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
