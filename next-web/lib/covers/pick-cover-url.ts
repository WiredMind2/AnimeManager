export type CoverVariant = {
  url?: string;
  size?: string;
  width?: number | null;
  height?: number | null;
};

const SIZE_RANK: Record<string, number> = {
  small: 1,
  medium: 2,
  large: 3,
  original: 4,
};

export function neededCoverPx(
  cssPx: number,
  devicePixelRatio = 1,
): number {
  const css = Number(cssPx);
  const dpr = Number(devicePixelRatio);
  if (!Number.isFinite(css) || css <= 0) return 0;
  const ratio = Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
  return Math.max(1, Math.round(css * ratio));
}

function variantWidth(variant: CoverVariant): number | null {
  const width = variant.width;
  if (width == null) return null;
  const value = Number(width);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function variantUrl(variant: CoverVariant): string | null {
  const url = (variant.url || "").trim();
  return url || null;
}

function variantSizeRank(variant: CoverVariant): number {
  return SIZE_RANK[String(variant.size || "medium")] || 0;
}

/** Smallest cover with width >= neededPx; otherwise the largest. */
export function pickCoverUrl(
  variants: CoverVariant[] | null | undefined,
  neededPx: number,
  fallback?: string | null,
): string | null {
  const sized: Array<[number, string]> = [];
  const unsized: Array<[number, string]> = [];

  for (const variant of variants || []) {
    const url = variantUrl(variant);
    if (!url) continue;
    const width = variantWidth(variant);
    if (width != null) {
      sized.push([width, url]);
    } else {
      unsized.push([variantSizeRank(variant), url]);
    }
  }

  if (sized.length > 0) {
    const needed = Math.max(0, Math.floor(Number(neededPx) || 0));
    const adequate = sized.filter(([width]) => width >= needed);
    if (adequate.length > 0) {
      adequate.sort((a, b) => a[0] - b[0]);
      return adequate[0][1];
    }
    sized.sort((a, b) => b[0] - a[0]);
    return sized[0][1];
  }

  if (unsized.length > 0) {
    unsized.sort((a, b) => b[0] - a[0]);
    return unsized[0][1];
  }

  const fallbackUrl = (fallback || "").trim();
  return fallbackUrl || null;
}
