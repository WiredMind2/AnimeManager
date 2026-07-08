import { Suspense } from "react";
import { ToastProvider } from "@/components/Toast";
import Rail from "./Rail";
import TopBar from "./TopBar";
import type { FilterValue, NavKey } from "@/lib/config";

type AppShellProps = {
  children: React.ReactNode;
  activeNav?: NavKey;
  activeFilter?: FilterValue;
  pageTitle?: string;
  topbarActions?: React.ReactNode;
  showSearch?: boolean;
  flash?: { kind: string; message: string } | null;
};

export default function AppShell({
  children,
  activeNav = "library",
  activeFilter,
  pageTitle,
  topbarActions,
  showSearch = true,
  flash,
}: AppShellProps) {
  return (
    <ToastProvider>
      <div className="shell">
        <Suspense fallback={null}>
          <Rail activeNav={activeNav} activeFilter={activeFilter} />
        </Suspense>
        <main className="main">
          <Suspense fallback={null}>
            <TopBar title={pageTitle} actions={topbarActions} showSearch={showSearch} />
          </Suspense>
          <div className="content">
            {flash ? <div className={`flash flash--${flash.kind}`}>{flash.message}</div> : null}
            {children}
          </div>
        </main>
      </div>
    </ToastProvider>
  );
}
