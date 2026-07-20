"use client";

import { useState } from "react";
import TopSelectorModal from "./TopSelectorModal";

export default function TopBrowseChip() {
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
        Top
      </button>
      <TopSelectorModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
