/**
 * Schema-driven settings form builder — TypeScript port of clients/http/settings_form.py.
 */

export const SECTION_ORDER = [
  "anime",
  "downloads",
  "file_managers",
  "torrent_managers",
  "database_managers",
  "media",
  "api_credentials",
  "playback",
  "database",
  "api",
  "ui",
  "paths",
  "feature_flags",
  "phoneSyncServer",
  "player",
  "logs",
  "UI",
  "windows",
] as const;

export const SECTION_TIERS: Record<string, number> = {
  anime: 1,
  downloads: 1,
  file_managers: 1,
  torrent_managers: 1,
  database_managers: 1,
  media: 1,
  api_credentials: 1,
  playback: 1,
  database: 2,
  api: 2,
  ui: 2,
  paths: 2,
  feature_flags: 2,
  phoneSyncServer: 2,
  player: 3,
  logs: 3,
  UI: 3,
  windows: 3,
};

export const SECTION_META: Record<string, { label: string; description: string }> = {
  anime: {
    label: "Library",
    description: "Pagination, schedule and publisher preferences.",
  },
  downloads: {
    label: "Downloads",
    description: "Default destination and concurrency for new downloads.",
  },
  file_managers: {
    label: "File managers",
    description: "Local-disk and FTP destinations for the library.",
  },
  torrent_managers: {
    label: "Torrent managers",
    description:
      'Configured torrent clients; pick the active one with "Last torrent manager used".',
  },
  database_managers: {
    label: "Database managers",
    description:
      'Configured database backends; pick the active one with "Last database used".',
  },
  media: {
    label: "Media players",
    description: "Preferred external players, in priority order.",
  },
  api_credentials: {
    label: "API credentials",
    description: "OAuth client IDs/secrets for metadata providers.",
  },
  playback: {
    label: "Playback",
    description: "In-browser HLS transcoding. Changes require an app restart.",
  },
  database: {
    label: "Database (active)",
    description: "Connection used by the embedded backend at runtime.",
  },
  api: {
    label: "API",
    description: "Timeouts and rate limits for outbound API calls.",
  },
  ui: {
    label: "Interface",
    description: "Basic UI preferences for the web/desktop client.",
  },
  paths: {
    label: "Paths",
    description: "Override paths for cache, icons and logs (blank = default).",
  },
  feature_flags: {
    label: "Feature flags",
    description: "Enable or disable behaviour gated behind compatibility flags.",
  },
  phoneSyncServer: {
    label: "Phone sync server",
    description: "Optional companion server for the mobile app.",
  },
  player: {
    label: "Player key bindings (legacy)",
    description: "Internal-player key bindings and fallback order, used by the Tk UI.",
  },
  logs: {
    label: "Logging",
    description: "Log channels and the in-memory log buffer size.",
  },
  UI: {
    label: "Theme & color palette (legacy)",
    description: "Color tokens, tag colors and state markers shared with the Tk UI.",
  },
  windows: {
    label: "Windows (Tk UI)",
    description: "Minimum sizes / titles for the legacy desktop windows.",
  },
};

const LEAF_LABELS: Record<string, string> = {
  url: "URL",
  dataPath: "Data path",
  dbPath: "Database path",
  iconPath: "Icon path",
  logsPath: "Logs path",
  client_id: "Client ID",
  client_secret: "Client secret",
  qb_settings: "qBittorrent extra settings",
  hostName: "Host name",
  serverPort: "Server port",
  apiHost: "API host",
  last_fm_used: "Last file manager used",
  last_tm_used: "Last torrent manager used",
  last_db_used: "Last database used",
  default_folder: "Default download folder",
  default_player: "Default player",
  players_order: "Players order",
  playerOrder: "Player fallback order",
  playerKeyBindings: "Player key bindings",
  rate_limit: "Rate limit (per minute)",
  timeout: "Timeout (seconds)",
  max_concurrent: "Max concurrent downloads",
  scheduleTimeout: "Schedule refresh interval (seconds, minimum 86400)",
  lastSchedule: "Last schedule (epoch)",
  scheduleRecencyDays: "Schedule recency window (days)",
  maxTimeout: "Max timeout (seconds)",
  maxTrendingAnime: "Max trending anime",
  animePerRow: "Anime per row",
  animePerPage: "Anime per page",
  topPublishers: "Top publishers",
  hideRated: "Hide rated entries",
  logBracketWidth: "Log bracket width",
  maxLogsSize: "Max logs size",
  window_size: "Window size (W × H)",
  enableServer: "Enable server",
  fileMarkers: "File markers (regex per color)",
  dateStates: "Airing-date states",
  tagcolors: "Tag colors",
  torrentsStateColors: "Torrent state colors",
  video_encoder: "Video encoder (auto, libx264, h264_nvenc, h264_qsv, h264_amf, h264_mf)",
};

const PASSWORD_TOKENS = ["password", "secret", "token", "api_key", "apikey"];

const PATH_LEAF_NAMES = new Set([
  "cache",
  "default_folder",
  "datapath",
  "dbpath",
  "iconpath",
  "logspath",
  "path",
]);

const HEX_COLOR_RE = /^#[0-9a-fA-F]{6}$/;
const TRUE_STRINGS = new Set(["1", "true", "yes", "on", "y", "t"]);
const MISSING = Symbol("missing");

export type MultiChoiceOption = {
  value: string;
  label: string;
  description?: string;
};

export type FieldNode =
  | GroupNode
  | BoolField
  | IntField
  | FloatField
  | PasswordField
  | SelectField
  | ColorField
  | ColorRefField
  | PathField
  | MultiChoiceField
  | ListField
  | JsonField
  | TextField;

export type GroupNode = {
  kind: "group";
  name: string;
  label: string;
  children: FieldNode[];
  depth: number;
  leaf_count: number;
  is_bool_only: boolean;
};

export type SectionNode = GroupNode & {
  section_label: string;
  description: string;
  tier: number;
  open_by_default: boolean;
};

type ScalarFieldBase = { name: string; label: string };

export type BoolField = ScalarFieldBase & { kind: "bool"; value: boolean };
export type IntField = ScalarFieldBase & { kind: "int"; value: number };
export type FloatField = ScalarFieldBase & { kind: "float"; value: number };
export type PasswordField = ScalarFieldBase & { kind: "password"; value: string };
export type SelectField = ScalarFieldBase & {
  kind: "select";
  value: string;
  options: string[];
};
export type ColorField = ScalarFieldBase & { kind: "color"; value: string };
export type ColorRefField = ScalarFieldBase & {
  kind: "color_ref";
  value: string;
  options: string[];
  palette: Record<string, string>;
};
export type PathField = ScalarFieldBase & { kind: "path"; value: string };
export type MultiChoiceField = ScalarFieldBase & {
  kind: "multi_choice";
  value: string[];
  /** Uppercase selected values (serializable for RSC props). */
  selected: string[];
  options: MultiChoiceOption[];
};
export type ListField = ScalarFieldBase & {
  kind: "list";
  elem_kind: string;
  value: string;
};
export type JsonField = ScalarFieldBase & { kind: "json"; value: string };
export type TextField = ScalarFieldBase & { kind: "str"; value: string };

type FormContext = {
  color_palette: Record<string, string>;
  color_hex_paths: Set<string>;
  color_ref_paths: Set<string>;
  select_sources: Record<string, string[]>;
  multi_choice_sources: Record<string, MultiChoiceOption[]>;
};

export type BuildSectionsOptions = {
  logCategories?: string[];
};

function humanize(key: string): string {
  if (!key) return "";
  if (key in LEAF_LABELS) return LEAF_LABELS[key];
  if (key === key.toUpperCase() && key.length > 1) return key;
  const spaced = key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : key;
}

function isPasswordField(name: string): boolean {
  const last = name.split(".").pop()?.toLowerCase() ?? "";
  return PASSWORD_TOKENS.some((tok) => last.includes(tok));
}

function isPathField(name: string): boolean {
  const last = name.split(".").pop() ?? "";
  const lower = last.toLowerCase();
  if (PATH_LEAF_NAMES.has(lower)) return true;
  return (
    lower.endsWith("path") || lower.endsWith("folder") || lower.endsWith("directory")
  );
}

function buildColorPalette(current: Record<string, unknown>): Record<string, string> {
  const palette: Record<string, string> = {};
  const ui = current.UI;
  if (!ui || typeof ui !== "object" || Array.isArray(ui)) return palette;
  const colors = (ui as Record<string, unknown>).colors;
  if (!colors || typeof colors !== "object" || Array.isArray(colors)) return palette;
  for (const [name, value] of Object.entries(colors as Record<string, unknown>)) {
    if (typeof value === "string" && HEX_COLOR_RE.test(value)) {
      palette[name] = value;
    }
  }
  return palette;
}

function buildColorHexPaths(current: Record<string, unknown>): Set<string> {
  const paths = new Set<string>();
  const ui = current.UI;
  if (!ui || typeof ui !== "object" || Array.isArray(ui)) return paths;
  const colors = (ui as Record<string, unknown>).colors;
  if (!colors || typeof colors !== "object" || Array.isArray(colors)) return paths;
  for (const [name, value] of Object.entries(colors as Record<string, unknown>)) {
    if (typeof value === "string" && HEX_COLOR_RE.test(value)) {
      paths.add(`UI.colors.${name}`);
    }
  }
  return paths;
}

function buildColorRefPaths(current: Record<string, unknown>): Set<string> {
  const paths = new Set<string>();
  const ui = current.UI;
  if (!ui || typeof ui !== "object" || Array.isArray(ui)) return paths;
  const uiObj = ui as Record<string, unknown>;

  const tagcolors = uiObj.tagcolors;
  if (tagcolors && typeof tagcolors === "object" && !Array.isArray(tagcolors)) {
    for (const key of Object.keys(tagcolors as Record<string, unknown>)) {
      paths.add(`UI.tagcolors.${key}`);
    }
  }

  const tsc = uiObj.torrentsStateColors;
  if (tsc && typeof tsc === "object" && !Array.isArray(tsc)) {
    for (const key of Object.keys(tsc as Record<string, unknown>)) {
      paths.add(`UI.torrentsStateColors.${key}`);
    }
  }

  const ds = uiObj.dateStates;
  if (ds && typeof ds === "object" && !Array.isArray(ds)) {
    for (const [state, body] of Object.entries(ds as Record<string, unknown>)) {
      if (body && typeof body === "object" && !Array.isArray(body) && "color" in body) {
        paths.add(`UI.dateStates.${state}.color`);
      }
    }
  }
  return paths;
}

function buildSelectSources(current: Record<string, unknown>): Record<string, string[]> {
  const sources: Record<string, string[]> = {};

  for (const [sectionKey, candidate] of [
    ["file_managers", "last_fm_used"],
    ["torrent_managers", "last_tm_used"],
    ["database_managers", "last_db_used"],
  ] as const) {
    const sect = current[sectionKey];
    if (sect && typeof sect === "object" && !Array.isArray(sect)) {
      const options = Object.keys(sect as Record<string, unknown>)
        .filter((k) => k !== candidate && !k.startsWith("_"))
        .sort();
      if (options.length) sources[`${sectionKey}.${candidate}`] = options;
    }
  }

  const media = current.media;
  if (media && typeof media === "object" && !Array.isArray(media)) {
    const order = (media as Record<string, unknown>).players_order;
    if (Array.isArray(order) && order.length) {
      sources["media.default_player"] = [...new Set(order.map(String))];
    }
  }

  sources["playback.video_encoder"] = [
    "auto",
    "libx264",
    "h264_nvenc",
    "h264_qsv",
    "h264_amf",
    "h264_mf",
  ];

  return sources;
}

function listElementKind(value: unknown[]): string {
  if (!value.length) return "str";
  if (value.every((v) => typeof v === "boolean")) return "bool";
  if (value.every((v) => typeof v === "number" && Number.isInteger(v))) return "int";
  if (value.every((v) => typeof v === "number")) return "float";
  if (value.every((v) => typeof v === "string")) return "str";
  return "mixed";
}

function listValueText(value: unknown[], elemKind: string): string {
  if (elemKind === "mixed") return JSON.stringify(value, null, 2);
  return value.map((v) => (v == null ? "" : String(v))).join("\n");
}

function buildLeaf(name: string, value: unknown, ctx: FormContext): FieldNode {
  const label = humanize(name.split(".").pop() ?? name);

  const multiOptions = ctx.multi_choice_sources[name];
  if (multiOptions) {
    let rawValue: string[] = [];
    if (Array.isArray(value)) rawValue = value.map(String);
    else if (typeof value === "string" && value) rawValue = [value];
    const selected = rawValue.map((v) => v.toUpperCase());
    return {
      kind: "multi_choice",
      name,
      label,
      value: rawValue,
      selected,
      options: multiOptions,
    };
  }

  if (typeof value === "boolean") {
    return { kind: "bool", name, label, value };
  }
  if (typeof value === "number" && Number.isInteger(value)) {
    return { kind: "int", name, label, value };
  }
  if (typeof value === "number") {
    return { kind: "float", name, label, value };
  }

  const selectOptions = ctx.select_sources[name];
  if (selectOptions && typeof value === "string") {
    return { kind: "select", name, label, value, options: [...selectOptions] };
  }

  if (typeof value === "string" && ctx.color_ref_paths.has(name)) {
    return {
      kind: "color_ref",
      name,
      label,
      value,
      options: Object.keys(ctx.color_palette),
      palette: { ...ctx.color_palette },
    };
  }

  if (typeof value === "string" && ctx.color_hex_paths.has(name)) {
    const normalized = HEX_COLOR_RE.test(value) ? value : "#000000";
    return { kind: "color", name, label, value: normalized };
  }

  if (typeof value === "string" && isPathField(name)) {
    return { kind: "path", name, label, value };
  }

  if (Array.isArray(value)) {
    const elemKind = listElementKind(value);
    return {
      kind: elemKind === "mixed" ? "json" : "list",
      name,
      label,
      elem_kind: elemKind,
      value: listValueText(value, elemKind),
    };
  }

  if (value == null) {
    return { kind: "str", name, label, value: "" };
  }
  if (typeof value === "string") {
    return {
      kind: isPasswordField(name) ? "password" : "str",
      name,
      label,
      value,
    };
  }

  return { kind: "json", name, label, value: JSON.stringify(value, null, 2) };
}

function buildGroup(prefix: string, value: unknown, depth: number, ctx: FormContext): FieldNode {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const children = Object.entries(value as Record<string, unknown>).map(([k, v]) =>
      buildGroup(prefix ? `${prefix}.${k}` : k, v, depth + 1, ctx),
    );
    const leafCount = children.filter((c) => c.kind !== "group").length;
    const isBoolOnly = children.length > 0 && children.every((c) => c.kind === "bool");
    return {
      kind: "group",
      name: prefix,
      label: prefix ? humanize(prefix.split(".").pop() ?? prefix) : "",
      children,
      depth,
      leaf_count: leafCount,
      is_bool_only: isBoolOnly,
    };
  }
  return buildLeaf(prefix, value, ctx);
}

export function buildContext(
  settings: Record<string, unknown>,
  options?: BuildSectionsOptions,
): FormContext {
  const palette = buildColorPalette(settings);
  const logCategories = options?.logCategories ?? [];
  const multiSources: Record<string, MultiChoiceOption[]> = {
    "logs.enabled_categories": logCategories.map((cat) => ({
      value: cat,
      label: cat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      description: "",
    })),
  };

  return {
    color_palette: palette,
    color_hex_paths: buildColorHexPaths(settings),
    color_ref_paths: buildColorRefPaths(settings),
    select_sources: buildSelectSources(settings),
    multi_choice_sources: multiSources,
  };
}

function seedVirtualKeys(
  settings: Record<string, unknown>,
  logCategories: string[],
): Record<string, unknown> {
  const seeded = structuredClone(settings) as Record<string, unknown>;
  let logsSection = seeded.logs;
  if (!logsSection || typeof logsSection !== "object" || Array.isArray(logsSection)) {
    logsSection = {};
    seeded.logs = logsSection;
  }
  const logs = logsSection as Record<string, unknown>;
  if (!("enabled_categories" in logs)) {
    logs.enabled_categories = [...logCategories];
  }
  return seeded;
}

export function buildSections(
  settings: Record<string, unknown>,
  options?: BuildSectionsOptions,
): SectionNode[] {
  if (!settings || typeof settings !== "object") return [];

  const logCategories = options?.logCategories ?? [];
  const seeded = seedVirtualKeys(settings, logCategories);
  const ctx = buildContext(seeded, options);

  const keys = Object.keys(seeded);
  const ordered = [
    ...SECTION_ORDER.filter((k) => keys.includes(k)),
    ...keys.filter((k) => !SECTION_ORDER.includes(k as (typeof SECTION_ORDER)[number])),
  ];

  return ordered.map((key) => {
    const node = buildGroup(key, seeded[key], 0, ctx) as SectionNode;
    const meta = SECTION_META[key] ?? {};
    const tier = SECTION_TIERS[key] ?? 2;
    node.section_label = meta.label ?? humanize(key);
    node.description = meta.description ?? "";
    node.tier = tier;
    node.open_by_default = tier === 1;
    return node;
  });
}

function getPath(root: Record<string, unknown>, dotted: string): unknown {
  const parts = dotted.split(".");
  let cur: unknown = root;
  for (const p of parts) {
    if (!cur || typeof cur !== "object" || Array.isArray(cur) || !(p in cur)) {
      return MISSING;
    }
    cur = (cur as Record<string, unknown>)[p];
  }
  return cur;
}

function setPath(root: Record<string, unknown>, dotted: string, value: unknown): void {
  const parts = dotted.split(".");
  let cur: Record<string, unknown> = root;
  for (const p of parts.slice(0, -1)) {
    let nxt = cur[p];
    if (!nxt || typeof nxt !== "object" || Array.isArray(nxt)) {
      nxt = {};
      cur[p] = nxt;
    }
    cur = nxt as Record<string, unknown>;
  }
  cur[parts[parts.length - 1]] = value;
}

function coerceInt(raw: string, fallback: number): number {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return 0;
  const n = Number.parseInt(trimmed, 10);
  if (!Number.isNaN(n)) return n;
  const f = Number.parseFloat(trimmed);
  return Number.isNaN(f) ? fallback : Math.trunc(f);
}

function coerceFloat(raw: string, fallback: number): number {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return 0;
  const n = Number.parseFloat(trimmed);
  return Number.isNaN(n) ? fallback : n;
}

function coerceBool(raw: string): boolean {
  return TRUE_STRINGS.has((raw ?? "").trim().toLowerCase());
}

function coerceList(raw: string, elemKind: string, fallback: unknown[]): unknown[] {
  if (elemKind === "mixed") {
    const text = (raw ?? "").trim();
    if (!text) return [];
    try {
      const parsed = JSON.parse(text);
      return Array.isArray(parsed) ? parsed : [...fallback];
    } catch {
      return [...fallback];
    }
  }

  const out: unknown[] = [];
  for (const line of (raw ?? "").split("\n")) {
    const token = line.trim();
    if (!token) continue;
    if (elemKind === "int") out.push(coerceInt(token, 0));
    else if (elemKind === "float") out.push(coerceFloat(token, 0));
    else if (elemKind === "bool") out.push(coerceBool(token));
    else out.push(token);
  }
  return out;
}

function formGetList(form: FormData, key: string): string[] {
  return form.getAll(key).map((v) => String(v));
}

export function parseForm(
  form: FormData,
  current: Record<string, unknown>,
  options?: BuildSectionsOptions,
): Record<string, unknown> {
  const logCategories = options?.logCategories ?? [];
  const seeded = seedVirtualKeys(current, logCategories);
  const result = structuredClone(seeded) as Record<string, unknown>;

  const boolNames = new Set(formGetList(form, "__bool__"));
  const multiNames = new Set(formGetList(form, "__multi__"));
  const keysPresent = new Set<string>();
  form.forEach((_, key) => keysPresent.add(key));

  for (const name of boolNames) {
    if (getPath(seeded, name) === MISSING) continue;
    setPath(result, name, keysPresent.has(name));
  }

  for (const name of multiNames) {
    if (getPath(seeded, name) === MISSING) continue;
    const values = formGetList(form, name)
      .map((v) => v.trim())
      .filter(Boolean);
    const seen = new Set<string>();
    const deduped: string[] = [];
    for (const v of values) {
      if (!seen.has(v)) {
        seen.add(v);
        deduped.push(v);
      }
    }
    setPath(result, name, deduped);
  }

  const seen = new Set([...boolNames, ...multiNames]);
  form.forEach((raw, key) => {
    if (!key || key.startsWith("__") || key === "settings_json") return;
    if (seen.has(key)) return;
    seen.add(key);

    const original = getPath(seeded, key);
    if (original === MISSING) return;

    const rawStr = String(raw ?? "");

    if (typeof original === "boolean") {
      if (!boolNames.has(key)) setPath(result, key, coerceBool(rawStr));
      return;
    }
    if (typeof original === "number" && Number.isInteger(original)) {
      setPath(result, key, coerceInt(rawStr, original));
      return;
    }
    if (typeof original === "number") {
      setPath(result, key, coerceFloat(rawStr, original));
      return;
    }
    if (Array.isArray(original)) {
      const elemKind = listElementKind(original);
      setPath(result, key, coerceList(rawStr, elemKind, original));
      return;
    }
    if (original && typeof original === "object") return;
    if (original == null || typeof original === "string") {
      setPath(result, key, rawStr);
      return;
    }
    try {
      setPath(result, key, JSON.parse(rawStr));
    } catch {
      setPath(result, key, rawStr);
    }
  });

  return result;
}

export function fieldDomId(name: string): string {
  return `f-${name}`;
}

export function colorTextDomId(name: string): string {
  return `t-${name}`;
}
