import AppShell from "@/components/shell/AppShell";
import { PageHeadSkeleton, PanelSkeleton } from "@/components/shell/RouteSkeletons";

export default function SettingsLoading() {
  return (
    <AppShell activeNav="settings" pageTitle="Settings" showSearch={false}>
      <PageHeadSkeleton />
      <PanelSkeleton rows={10} />
    </AppShell>
  );
}
