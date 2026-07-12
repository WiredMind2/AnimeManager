import { trackEvent } from "@/lib/telemetry/client";

type WebVitalMetric = {
  name: string;
  value: number;
  id: string;
  rating?: string;
};

function reportMetric(metric: WebVitalMetric): void {
  trackEvent(`web_vital.${metric.name.toLowerCase()}`, "info", {
    value: metric.value,
    metric_id: metric.id,
    rating: metric.rating,
  });
}

export function startWebVitalsReporting(): void {
  if (typeof window === "undefined") {
    return;
  }
  void import("web-vitals")
    .then(({ onCLS, onINP, onLCP, onTTFB }) => {
      onLCP((metric) => reportMetric(metric));
      onINP((metric) => reportMetric(metric));
      onCLS((metric) => reportMetric(metric));
      onTTFB((metric) => reportMetric(metric));
    })
    .catch(() => {
      /* web-vitals optional at runtime */
    });
}
