import type { ReactNode } from "react";

import { Rail } from "@/components/layout/rail";
import { Topbar } from "@/components/layout/topbar";

export function ShellLayout({
  activeNav,
  activeFilter,
  pageTitle,
  topbarTitle,
  topbarQuery,
  flash,
  topbarActions,
  children,
}: {
  activeNav?: string;
  activeFilter?: string;
  pageTitle?: string;
  topbarTitle?: string;
  topbarQuery?: string;
  flash?: { kind: string; message: string } | null;
  topbarActions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="shell">
      <Rail activeNav={activeNav} activeFilter={activeFilter} />
      <main className="main">
        <Topbar
          title={topbarTitle || pageTitle || "Library"}
          filter={activeFilter}
          query={topbarQuery}
          actions={topbarActions}
        />
        <div className="content">
          {flash ? (
            <div className={`flash flash--${flash.kind}`}>{flash.message}</div>
          ) : null}
          {children}
        </div>
      </main>
    </div>
  );
}
