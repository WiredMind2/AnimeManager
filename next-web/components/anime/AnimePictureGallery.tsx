"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { AnimePicture } from "@/lib/api";
import { useDialogBehavior } from "@/lib/use-dialog";
import "./AnimePictureGallery.css";

type AnimePictureGalleryProps = {
  pictures: AnimePicture[];
  title?: string;
};

const SIZE_ORDER = ["large", "medium", "small", "original"];
const INITIAL_VISIBLE = 12;

export default function AnimePictureGallery({ pictures, title }: AnimePictureGalleryProps) {
  const [activeUrl, setActiveUrl] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const sorted = useMemo(
    () =>
      [...pictures].sort((a, b) => {
        const ai = SIZE_ORDER.indexOf((a.size || "").toLowerCase());
        const bi = SIZE_ORDER.indexOf((b.size || "").toLowerCase());
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      }),
    [pictures],
  );

  const hero = activeUrl || sorted[0]?.url;
  const heroIndex = Math.max(0, sorted.findIndex((pic) => pic.url === hero));
  const visible = showAll ? sorted : sorted.slice(0, INITIAL_VISIBLE);
  const hiddenCount = sorted.length - visible.length;

  const closeLightbox = useCallback(() => setLightboxOpen(false), []);
  const { panelRef } = useDialogBehavior<HTMLDivElement>({
    open: lightboxOpen,
    onClose: closeLightbox,
  });

  const stepLightbox = useCallback(
    (delta: number) => {
      if (sorted.length === 0) return;
      const nextIndex = (heroIndex + delta + sorted.length) % sorted.length;
      setActiveUrl(sorted[nextIndex]?.url || null);
    },
    [heroIndex, sorted],
  );

  useEffect(() => {
    if (!lightboxOpen) return undefined;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "ArrowLeft") stepLightbox(-1);
      if (event.key === "ArrowRight") stepLightbox(1);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [lightboxOpen, stepLightbox]);

  if (sorted.length === 0) return null;

  const altBase = title ? `${title} artwork` : "Anime artwork";
  const heroPic = sorted[heroIndex];
  const heroAlt = heroPic?.size ? `${altBase} (${heroPic.size})` : altBase;

  return (
    <section className="detail__section" id="anime-gallery">
      <div className="detail__section-title">
        <h3>Pictures</h3>
        <span className="meta">
          {sorted.length} image{sorted.length === 1 ? "" : "s"}
        </span>
      </div>

      {hero ? (
        <div
          className="detail__gallery-hero"
          role="button"
          tabIndex={0}
          onClick={() => setLightboxOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setLightboxOpen(true);
            }
          }}
          aria-label="View full-size image"
        >
          <img src={hero} alt={heroAlt} referrerPolicy="no-referrer" />
        </div>
      ) : null}

      <div className="detail__gallery-thumbs">
        {visible.map((pic) => (
          <button
            key={`${pic.size}-${pic.url}`}
            type="button"
            className={`detail__gallery-thumb${hero === pic.url ? " detail__gallery-thumb--active" : ""}`}
            onClick={() => setActiveUrl(pic.url || null)}
          >
            {pic.url ? (
              <span className="detail__gallery-thumb-media">
                <img
                  src={pic.url}
                  alt={pic.size ? `${altBase} (${pic.size})` : altBase}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
              </span>
            ) : null}
            <span>{pic.size || "image"}</span>
          </button>
        ))}
      </div>

      {hiddenCount > 0 || showAll ? (
        <button
          type="button"
          className="btn btn--ghost detail__gallery-more"
          onClick={() => setShowAll((value) => !value)}
        >
          {showAll ? "Show fewer" : `Show all ${sorted.length}`}
        </button>
      ) : null}

      {lightboxOpen && hero ? (
        <div className="modal" role="dialog" aria-modal="true" aria-label="Picture viewer">
          <div className="modal__backdrop" onClick={closeLightbox} />
          <div className="modal__dialog modal__dialog--lightbox" role="document" ref={panelRef}>
            <header className="modal__header">
              <h2 className="modal__title">{heroAlt}</h2>
              <button
                className="modal__close"
                type="button"
                aria-label="Close"
                onClick={closeLightbox}
              >
                ×
              </button>
            </header>
            <div className="modal__body modal__body--panel">
              <div className="detail__lightbox-stage">
                {sorted.length > 1 ? (
                  <button
                    type="button"
                    className="detail__lightbox-nav detail__lightbox-nav--prev"
                    aria-label="Previous image"
                    onClick={() => stepLightbox(-1)}
                  >
                    ‹
                  </button>
                ) : null}
                <img src={hero} alt={heroAlt} referrerPolicy="no-referrer" />
                {sorted.length > 1 ? (
                  <button
                    type="button"
                    className="detail__lightbox-nav detail__lightbox-nav--next"
                    aria-label="Next image"
                    onClick={() => stepLightbox(1)}
                  >
                    ›
                  </button>
                ) : null}
              </div>
              {sorted.length > 1 ? (
                <p className="detail__lightbox-count">
                  {heroIndex + 1} / {sorted.length}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
