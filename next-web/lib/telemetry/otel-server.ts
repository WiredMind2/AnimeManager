/**
 * Optional OpenTelemetry init for the Next.js Node.js runtime (SSR / API routes).
 * Gated on OTEL_EXPORTER_OTLP_ENDPOINT — no-op when unset.
 */

let started = false;

export function initOtelServer(): void {
  if (started) {
    return;
  }
  const endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT?.trim();
  if (!endpoint) {
    return;
  }

  // Dynamic require keeps the module out of client bundles.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { NodeSDK } = require("@opentelemetry/sdk-node") as typeof import("@opentelemetry/sdk-node");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { OTLPTraceExporter } = require("@opentelemetry/exporter-trace-otlp-http") as typeof import("@opentelemetry/exporter-trace-otlp-http");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { HttpInstrumentation } = require("@opentelemetry/instrumentation-http") as typeof import("@opentelemetry/instrumentation-http");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { resourceFromAttributes } = require("@opentelemetry/resources") as typeof import("@opentelemetry/resources");

  const serviceName = process.env.OTEL_SERVICE_NAME?.trim() || "animemanager-next-web";

  const sdk = new NodeSDK({
    resource: resourceFromAttributes({
      "service.name": serviceName,
    }),
    traceExporter: new OTLPTraceExporter({
      url: endpoint.endsWith("/v1/traces") ? endpoint : `${endpoint}/v1/traces`,
    }),
    instrumentations: [new HttpInstrumentation()],
  });

  sdk.start();
  started = true;
}
