import AppShell from "@/components/shell/AppShell";
import { PageHeadSkeleton, PanelSkeleton } from "@/components/shell/RouteSkeletons";

export default function DownloadsLoading() {
  return (
    <AppShell activeNav="downloads" pageTitle="Downloads" showSearch={false}>
      <PageHeadSkeleton />
      <PanelSkeleton rows={8} />
    </AppShell>
  );
}
