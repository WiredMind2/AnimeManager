"use client";

import { useState } from "react";
import SeasonSelectorModal from "./SeasonSelectorModal";

export default function SeasonBrowseChip() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className="chip"
        role="tab"
        aria-selected="false"
        onClick={() => setOpen(true)}
      >
        By season
      </button>
      <SeasonSelectorModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
