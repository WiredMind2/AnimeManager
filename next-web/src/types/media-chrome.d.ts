import "react";

type MediaElementProps = React.DetailedHTMLProps<
  React.HTMLAttributes<HTMLElement>,
  HTMLElement
> & {
  slot?: string;
  "seek-offset"?: string;
  "show-duration"?: string;
  fullscreenelement?: string;
};

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "media-controller": MediaElementProps;
      "media-loading-indicator": MediaElementProps;
      "media-control-bar": MediaElementProps;
      "media-play-button": MediaElementProps;
      "media-seek-backward-button": MediaElementProps;
      "media-seek-forward-button": MediaElementProps;
      "media-time-range": MediaElementProps;
      "media-time-display": MediaElementProps;
      "media-mute-button": MediaElementProps;
      "media-volume-range": MediaElementProps;
      "media-pip-button": MediaElementProps;
      "media-fullscreen-button": MediaElementProps;
    }
  }
}
