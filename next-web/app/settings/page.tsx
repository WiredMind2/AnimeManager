import AppShell from "@/components/shell/AppShell";
import SettingsForm from "@/components/settings/SettingsForm";
import { api } from "@/lib/api";
import { KNOWN_CATEGORIES, LOG_TAIL_INITIAL, mergeKnownCategories } from "@/lib/logs";
import { buildSections } from "@/lib/settings-form";

async function resolveLogCategories(
  settings: Record<string, unknown>,
): Promise<string[]> {
  let categories: string[] = [...KNOWN_CATEGORIES];
  const logs = settings.logs;
  if (logs && typeof logs === "object" && !Array.isArray(logs)) {
    const enabled = (logs as Record<string, unknown>).enabled_categories;
    if (Array.isArray(enabled)) {
      for (const cat of enabled.map(String)) {
        if (!categories.includes(cat)) categories.push(cat);
      }
    }
  }
  try {
    const data = await api.getLogsData({ limit: LOG_TAIL_INITIAL });
    categories = mergeKnownCategories(data.records ?? []);
  } catch {
    // Keep static + settings-derived categories when logs API is unavailable.
  }
  return categories;
}

export default async function SettingsPage() {
  let settings: Record<string, unknown> = {};
  try {
    settings = (await api.getSettings()) ?? {};
  } catch {
    settings = {};
  }

  const logCategories = await resolveLogCategories(settings);
  const sections = buildSections(settings, { logCategories });
  const currentSettingsJson = JSON.stringify(settings, null, 2);

  return (
    <AppShell activeNav="settings" pageTitle="Settings" showSearch={false}>
      <SettingsForm
        sections={sections}
        currentSettings={settings}
        currentSettingsJson={currentSettingsJson}
        logCategories={logCategories}
      />
    </AppShell>
  );
}
