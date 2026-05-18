import { AppShell } from "@/components/app-shell";
import { SettingsForm } from "@/components/settings/settings-form";
import { backendFetch } from "@/lib/backend";

type SettingsPayload = {
  sections: Array<Record<string, unknown>>;
};

export default async function SettingsPage() {
  const data = await backendFetch<SettingsPayload>("/ui/api/settings");

  return (
    <AppShell activeNav="settings" pageTitle="Settings">
      <header className="page-head">
        <div>
          <h1 className="page-head__title">Settings</h1>
          <p className="page-head__subtitle">
            Tune download paths, metadata providers, logging, and web playback options. Changes
            are written to <code>settings.json</code> through the embedded SDK.
          </p>
        </div>
      </header>

      <SettingsForm sections={data.sections as never} />
    </AppShell>
  );
}
