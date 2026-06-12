import { backendPath } from "./config";
import { parseForm, type BuildSectionsOptions } from "./settings-form";

export type SettingsSaveResult = {
  ok: boolean;
  message?: string;
  kind?: "success" | "error" | "info";
};

function extractFlashMessage(html: string): SettingsSaveResult | null {
  const doc = new DOMParser().parseFromString(html, "text/html");
  for (const kind of ["error", "success", "info"] as const) {
    const el = doc.querySelector(`.flash--${kind}`);
    if (el?.textContent?.trim()) {
      return {
        ok: kind !== "error",
        kind,
        message: el.textContent.trim(),
      };
    }
  }
  return null;
}

/**
 * POST form data to the legacy `/ui/settings` endpoint for full parity
 * with the Jinja settings page.
 */
export async function postSettingsForm(form: FormData): Promise<SettingsSaveResult> {
  const res = await fetch(backendPath("/ui/settings"), {
    method: "POST",
    body: form,
    cache: "no-store",
  });

  const html = await res.text();
  const flash = extractFlashMessage(html);
  if (flash) return flash;

  if (res.ok) {
    return { ok: true, kind: "success", message: "Settings saved." };
  }
  return {
    ok: false,
    kind: "error",
    message: `Save failed (${res.status}).`,
  };
}

export async function saveSettingsFromForm(
  form: FormData,
  current: Record<string, unknown>,
  options?: BuildSectionsOptions,
): Promise<{ result: SettingsSaveResult; updates?: Record<string, unknown> }> {
  const rawJson = String(form.get("settings_json") ?? "").trim();

  if (rawJson) {
    try {
      const parsed = JSON.parse(rawJson);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return {
          result: {
            ok: false,
            kind: "error",
            message: "Advanced JSON must be a top-level object.",
          },
        };
      }
      const submitForm = new FormData();
      submitForm.set("settings_json", rawJson);
      const result = await postSettingsForm(submitForm);
      return { result, updates: parsed as Record<string, unknown> };
    } catch (err) {
      const msg = err instanceof SyntaxError ? err.message : "Invalid JSON.";
      return {
        result: { ok: false, kind: "error", message: `Invalid JSON: ${msg}` },
      };
    }
  }

  const updates = parseForm(form, current, options);
  const result = await postSettingsForm(form);
  return { result, updates };
}

export type BrowseEntry = {
  name: string;
  path: string;
  isDir: boolean;
  sizeHuman?: string;
};

export type BrowseListing = {
  currentPath: string;
  parentPath?: string;
  entries: BrowseEntry[];
  error?: string;
};

export function parseBrowseHtml(html: string): BrowseListing {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const listing = doc.querySelector("[data-fb-listing]");
  const currentPath = listing?.getAttribute("data-fb-current-path") ?? "";
  const error = doc.querySelector(".fb-listing__error")?.textContent?.trim();

  const entries: BrowseEntry[] = [];
  doc.querySelectorAll(".fb-entry").forEach((el) => {
    const path = el.getAttribute("data-fb-path");
    if (!path) return;
    const nameEl = el.querySelector(".fb-entry__name");
    const metaEl = el.querySelector(".fb-entry__meta");
    entries.push({
      path,
      name: nameEl?.textContent?.trim() ?? path,
      isDir: el.classList.contains("fb-entry--dir") || el.classList.contains("fb-entry--up"),
      sizeHuman: metaEl?.textContent?.trim() || undefined,
    });
  });

  const parent = entries.find((e) => e.name.startsWith(".."));
  return {
    currentPath,
    parentPath: parent?.path,
    entries: entries.filter((e) => !e.name.startsWith("..")),
    error: error || undefined,
  };
}

export async function fetchBrowseDirectory(path = ""): Promise<BrowseListing> {
  const params = new URLSearchParams();
  if (path) params.set("path", path);
  const qs = params.toString();
  const url = backendPath(`/ui/browse${qs ? `?${qs}` : ""}`);
  const res = await fetch(url, {
    headers: { Accept: "text/html" },
    cache: "no-store",
  });
  if (!res.ok) {
    return {
      currentPath: path,
      entries: [],
      error: `Could not load directory (${res.status}).`,
    };
  }
  const html = await res.text();
  return parseBrowseHtml(html);
}
