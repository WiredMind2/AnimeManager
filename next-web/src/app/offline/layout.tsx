import type { ReactNode } from "react";

import { Rail } from "@/components/layout/rail";

/** Offline page uses a minimal shell (no backend-dependent topbar search). */
export default function OfflineLayout({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <Rail />
      <main className="main">
        <header className="topbar">
          <span className="topbar__title">Offline</span>
        </header>
        {children}
      </main>
    </div>
  );
}
