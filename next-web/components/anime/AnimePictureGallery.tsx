"use client";

import { useState } from "react";
import type { AnimePicture } from "@/lib/api";

type AnimePictureGalleryProps = {
  pictures: AnimePicture[];
};

const SIZE_ORDER = ["large", "medium", "small", "original"];

export default function AnimePictureGallery({ pictures }: AnimePictureGalleryProps) {
  const [activeUrl, setActiveUrl] = useState<string | null>(null);

  const sorted = [...pictures].sort((a, b) => {
    const ai = SIZE_ORDER.indexOf((a.size || "").toLowerCase());
    const bi = SIZE_ORDER.indexOf((b.size || "").toLowerCase());
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  if (sorted.length === 0) return null;

  const hero = activeUrl || sorted[0]?.url;

  return (
    <section className="detail__section detail__gallery">
      <div className="detail__section-title">
        <h3>Pictures</h3>
        <span className="meta">{sorted.length} image{sorted.length === 1 ? "" : "s"}</span>
      </div>

      {hero ? (
        <div className="detail__gallery-hero">
          <img src={hero} alt="Anime artwork" referrerPolicy="no-referrer" />
        </div>
      ) : null}

      <div className="detail__gallery-thumbs">
        {sorted.map((pic) => (
          <button
            key={`${pic.size}-${pic.url}`}
            type="button"
            className={`detail__gallery-thumb${hero === pic.url ? " detail__gallery-thumb--active" : ""}`}
            onClick={() => setActiveUrl(pic.url || null)}
          >
            {pic.url ? (
              <img src={pic.url} alt={pic.size || "picture"} referrerPolicy="no-referrer" />
            ) : null}
            <span>{pic.size || "image"}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
