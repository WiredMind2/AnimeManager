"use client";

import { useState } from "react";
import GenreSelectorModal from "./GenreSelectorModal";

export default function GenreBrowseChip() {
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
        By genre
      </button>
      <GenreSelectorModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
