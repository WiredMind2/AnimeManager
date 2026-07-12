"use client";

import { useEffect } from "react";
import { installGlobalErrorHandlers } from "@/lib/telemetry/errors";
import { startWebVitalsReporting } from "@/lib/telemetry/web-vitals";

type TelemetryProviderProps = {
  children: React.ReactNode;
};

export default function TelemetryProvider({ children }: TelemetryProviderProps) {
  useEffect(() => {
    installGlobalErrorHandlers();
    startWebVitalsReporting();
  }, []);

  return children;
}
