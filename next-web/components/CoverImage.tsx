"use client";

import {
  useLayoutEffect,
  useRef,
  useState,
  type ImgHTMLAttributes,
  type ReactNode,
} from "react";

type CoverImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> & {
  src: string;
  /** Shown when the image fails to load. */
  fallback?: ReactNode;
};

/**
 * Drop-in for poster/cover ``<img>`` tags. Shows a shimmer placeholder until
 * the image fires ``load``, then fades in. Parent should be ``position:
 * relative`` with ``overflow: hidden`` so the placeholder fills the slot.
 */
export default function CoverImage({
  src,
  alt = "",
  className,
  fallback = null,
  onLoad,
  onError,
  ...rest
}: CoverImageProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [status, setStatus] = useState<"loading" | "loaded" | "error">(
    "loading",
  );

  useLayoutEffect(() => {
    setStatus("loading");
    const img = imgRef.current;
    if (img?.complete && img.naturalWidth > 0) {
      setStatus("loaded");
    }
  }, [src]);

  if (status === "error") {
    return <>{fallback}</>;
  }

  const imgClass = [
    "cover-image__img",
    status === "loaded" ? "cover-image__img--ready" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      {status === "loading" ? (
        <span className="cover-image__placeholder" aria-hidden="true" />
      ) : null}
      <img
        {...rest}
        ref={imgRef}
        src={src}
        alt={alt}
        className={imgClass}
        onLoad={(event) => {
          setStatus("loaded");
          onLoad?.(event);
        }}
        onError={(event) => {
          setStatus("error");
          onError?.(event);
        }}
      />
    </>
  );
}
