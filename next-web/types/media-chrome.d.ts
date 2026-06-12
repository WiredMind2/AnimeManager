import type { DetailedHTMLProps, HTMLAttributes } from "react";

type MediaChromeAttrs = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement>;

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "media-controller": MediaChromeAttrs;
      "media-control-bar": MediaChromeAttrs;
      "media-play-button": MediaChromeAttrs & { "seek-offset"?: string };
      "media-seek-backward-button": MediaChromeAttrs & { "seek-offset"?: string };
      "media-seek-forward-button": MediaChromeAttrs & { "seek-offset"?: string };
      "media-time-range": MediaChromeAttrs;
      "media-time-display": MediaChromeAttrs & { "show-duration"?: boolean | "" };
      "media-mute-button": MediaChromeAttrs;
      "media-volume-range": MediaChromeAttrs;
      "media-pip-button": MediaChromeAttrs;
      "media-fullscreen-button": MediaChromeAttrs;
      "media-loading-indicator": MediaChromeAttrs & { slot?: string };
    }
  }
}

export {};
