/**
 * Inject W3C trace context (traceparent) into outbound fetch headers when
 * an active OpenTelemetry span exists (Next.js Node runtime).
 */

type HeaderCarrier = {
  set(name: string, value: string): void;
};

export function injectTraceHeaders(headers: Headers): void {
  if (typeof window !== "undefined") {
    return;
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const api = require("@opentelemetry/api") as typeof import("@opentelemetry/api");
    const carrier: HeaderCarrier = {
      set(name: string, value: string) {
        headers.set(name, value);
      },
    };
    api.propagation.inject(api.context.active(), carrier, {
      set(carrierObj, key, value) {
        (carrierObj as HeaderCarrier).set(key, value);
      },
    });
  } catch {
    /* OpenTelemetry not installed or no active context */
  }
}
