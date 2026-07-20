"""Schema-driven helpers for the structured settings page.

The web settings UI is rendered by walking the *current* settings dict
returned by ``ClientSDK.get_settings`` and producing a structured tree
of field descriptors that the Jinja template can iterate over. The
reverse path -- ``parse_form`` -- consumes a submitted form and uses
the current settings as a schema to coerce each value back into the
correct Python type.

Type inference is deliberately conservative: it only emits structured
inputs for the leaf types it can round-trip safely (``bool``, ``int``,
``float``, ``str``, homogeneous lists of scalars). Anything more
exotic (e.g. lists of dicts) falls back to a small JSON textarea so
the user can still edit it, while a top-level "raw JSON" textarea on
the settings page provides an unconditional escape hatch.

On top of that the builder layers a few *contextual* widget hints:

* hex color values under ``UI.colors`` render as a native color picker
  with a synced hex text input;
* color *references* (``UI.tagcolors.*``, ``UI.dateStates.*.color``,
  ``UI.torrentsStateColors.*``) render as a select populated from the
  available palette entries, with a swatch preview;
* path-shaped fields render alongside a "Browse…" button which opens
  the directory-picker modal backed by ``/ui/browse``;
* well-known "last X used" fields render as a select limited to the
  keys configured in their parent dict.

Because ``application.services.anime_service.update_settings`` only
performs a *shallow* merge over the top-level sections, ``parse_form``
returns a fully-rebuilt settings dict (current settings deep-copied
with form overrides applied) rather than a sparse delta. That keeps
unrelated nested keys intact across save round-trips.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Mapping, MutableMapping

# Top-level section ordering. Tier 1 sections come first and are
# expanded by default; tier 2 sections follow and are collapsed; tier 3
# (niche/legacy: Tk window sizes, color palette, etc.) come last and
# are collapsed.
SECTION_ORDER: tuple[str, ...] = (
    # Tier 1 -- daily-use settings.
    "anime",
    "downloads",
    "file_managers",
    "torrent_managers",
    "database_managers",
    "media",
    "api_credentials",
    "playback",
    "library_sync",
    # Tier 2 -- useful but rarely changed.
    "database",
    "api",
    "ui",
    "paths",
    "feature_flags",
    "phoneSyncServer",
    # Tier 3 -- niche or legacy.
    "player",
    "logs",
    "UI",
    "windows",
)

SECTION_TIERS: dict[str, int] = {
    "anime": 1,
    "downloads": 1,
    "file_managers": 1,
    "torrent_managers": 1,
    "database_managers": 1,
    "media": 1,
    "api_credentials": 1,
    "playback": 1,
    "library_sync": 1,
    "database": 2,
    "api": 2,
    "ui": 2,
    "paths": 2,
    "feature_flags": 2,
    "phoneSyncServer": 2,
    "player": 3,
    "logs": 3,
    "UI": 3,
    "windows": 3,
}

# Human labels for sections + a short description shown under each
# section heading. Keep these light -- the schema is meant to surface
# values, not duplicate the docs.
SECTION_META: dict[str, dict[str, str]] = {
    "anime": {
        "label": "Library",
        "description": "Pagination, schedule and publisher preferences.",
    },
    "downloads": {
        "label": "Downloads",
        "description": "Default destination and concurrency for new downloads.",
    },
    "file_managers": {
        "label": "File managers",
        "description": "Local-disk and FTP destinations for the library.",
    },
    "torrent_managers": {
        "label": "Torrent managers",
        "description": "Configured torrent clients; pick the active one with “Last torrent manager used”.",
    },
    "database_managers": {
        "label": "Database managers",
        "description": "Configured database backends; pick the active one with “Last database used”.",
    },
    "media": {
        "label": "Media players",
        "description": "Preferred external players, in priority order.",
    },
    "api_credentials": {
        "label": "API credentials",
        "description": "OAuth client IDs/secrets for metadata providers.",
    },
    "playback": {
        "label": "Playback",
        "description": "In-browser HLS transcoding. Changes require an app restart.",
    },
    "library_sync": {
        "label": "Library sync",
        "description": "Automatic tag promotion and SEEN-library cleanup on startup.",
    },
    "database": {
        "label": "Database (active)",
        "description": "Connection used by the embedded backend at runtime.",
    },
    "api": {
        "label": "API",
        "description": "Timeouts and rate limits for outbound API calls.",
    },
    "ui": {
        "label": "Interface",
        "description": "Basic UI preferences for the web/desktop client.",
    },
    "paths": {
        "label": "Paths",
        "description": "Override paths for cache, icons and logs (blank = default).",
    },
    "feature_flags": {
        "label": "Feature flags",
        "description": "Enable or disable behaviour gated behind compatibility flags.",
    },
    "phoneSyncServer": {
        "label": "Phone sync server",
        "description": "Optional companion server for the mobile app.",
    },
    "player": {
        "label": "Player key bindings (legacy)",
        "description": "Internal-player key bindings and fallback order, used by the Tk UI.",
    },
    "logs": {
        "label": "Logging",
        "description": "Log channels and the in-memory log buffer size.",
    },
    "UI": {
        "label": "Theme & color palette (legacy)",
        "description": "Color tokens, tag colors and state markers shared with the Tk UI.",
    },
    "windows": {
        "label": "Windows (Tk UI)",
        "description": "Minimum sizes / titles for the legacy desktop windows.",
    },
}

# A small dictionary of leaf-key labels that don't humanize cleanly via
# the generic camelCase/snake_case routine.
_LEAF_LABELS: dict[str, str] = {
    "url": "URL",
    "dataPath": "Data path",
    "dbPath": "Database path",
    "iconPath": "Icon path",
    "logsPath": "Logs path",
    "client_id": "Client ID",
    "client_secret": "Client secret",
    "qb_settings": "qBittorrent extra settings",
    "hostName": "Host name",
    "serverPort": "Server port",
    "apiHost": "API host",
    "last_fm_used": "Last file manager used",
    "last_tm_used": "Last torrent manager used",
    "last_db_used": "Last database used",
    "default_folder": "Default download folder",
    "default_player": "Default player",
    "players_order": "Players order",
    "playerOrder": "Player fallback order",
    "playerKeyBindings": "Player key bindings",
    "rate_limit": "Rate limit (per minute)",
    "timeout": "Timeout (seconds)",
    "max_concurrent": "Max concurrent downloads",
    "scheduleTimeout": "Schedule refresh interval (seconds, minimum 86400)",
    "lastSchedule": "Last schedule (epoch)",
    "scheduleRecencyDays": "Schedule recency window (days)",
    "maxTimeout": "Max timeout (seconds)",
    "maxTrendingAnime": "Max trending anime",
    "animePerRow": "Anime per row",
    "animePerPage": "Anime per page",
    "topPublishers": "Top publishers",
    "hideRated": "Hide rated entries",
    "logBracketWidth": "Log bracket width",
    "maxLogsSize": "Max logs size",
    "window_size": "Window size (W × H)",
    "enableServer": "Enable server",
    "fileMarkers": "File markers (regex per color)",
    "dateStates": "Airing-date states",
    "tagcolors": "Tag colors",
    "torrentsStateColors": "Torrent state colors",
    "video_encoder": "Video encoder (auto, libx264, h264_nvenc, h264_qsv, h264_amf, h264_mf)",
    "promote_watching_on_startup": "Promote NONE/WATCHLIST to WATCHING when local files exist",
    "purge_seen_on_startup": "Delete SEEN anime folders and torrents on startup",
}

# Substrings that mark a string field as a secret -> rendered as
# ``type="password"`` so the value isn't visible by default.
_PASSWORD_TOKENS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
)

# Known path-shaped leaf names. Anything in this set, or whose suffix
# matches /path|folder|directory/i, is rendered with a Browse button.
_PATH_LEAF_NAMES: frozenset[str] = frozenset(
    {
        "cache",
        "default_folder",
        "datapath",
        "dbpath",
        "iconpath",
        "logspath",
        "path",
    }
)

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


# ---------------------------------------------------------------------------
# Multi-choice (checkbox grid) registry
# ---------------------------------------------------------------------------
#
# Some list-shaped settings are semantically a *selection* of well-known
# options rather than a free-form string list. ``logs.disabled_categories``
# is the canonical example: the user picks which categories to silence
# from the live log viewer, so a checkbox grid is far friendlier than
# a textarea. The registry maps the dotted setting path to a *callable*
# that returns the available options (deferred so we can pull dynamic
# data like newly-observed categories at render time).


def _logs_category_options(_settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return ``[{value, label, description}, …]`` for log categories.

    Imported lazily so the settings module stays usable without the
    log-buffer subsystem present (e.g. in the Tk client).
    """
    try:
        from . import log_buffer  # type: ignore
    except ImportError:  # pragma: no cover - packaged install fallback
        try:
            from clients.http import log_buffer  # type: ignore
        except ImportError:
            return []
    return [
        {"value": cat, "label": cat.replace("_", " ").title(), "description": ""}
        for cat in log_buffer.global_buffer.known_categories()
    ]


_MULTI_CHOICE_SOURCES: dict[str, Any] = {
    "logs.enabled_categories": _logs_category_options,
}


# ---------------------------------------------------------------------------
# Labelling
# ---------------------------------------------------------------------------


def _humanize(key: str) -> str:
    """Convert a snake_case / camelCase key into a human label."""
    if not key:
        return ""
    if key in _LEAF_LABELS:
        return _LEAF_LABELS[key]
    if key.isupper():
        return key
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    s = s.replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else key


def _is_password_field(name: str) -> bool:
    last = name.rsplit(".", 1)[-1].lower()
    return any(tok in last for tok in _PASSWORD_TOKENS)


def _is_path_field(name: str) -> bool:
    last = name.rsplit(".", 1)[-1]
    lower = last.lower()
    if lower in _PATH_LEAF_NAMES:
        return True
    return (
        lower.endswith("path")
        or lower.endswith("folder")
        or lower.endswith("directory")
    )


# ---------------------------------------------------------------------------
# Context derivation (color palette, color references, select sources)
# ---------------------------------------------------------------------------


def _build_color_palette(current: Mapping[str, Any]) -> dict[str, str]:
    palette: dict[str, str] = {}
    ui = current.get("UI") if isinstance(current, Mapping) else None
    if not isinstance(ui, Mapping):
        return palette
    colors = ui.get("colors")
    if not isinstance(colors, Mapping):
        return palette
    for name, value in colors.items():
        if isinstance(value, str) and _HEX_COLOR_RE.match(value):
            palette[name] = value
    return palette


def _build_color_hex_paths(current: Mapping[str, Any]) -> set[str]:
    ui = current.get("UI") if isinstance(current, Mapping) else None
    if not isinstance(ui, Mapping):
        return set()
    colors = ui.get("colors")
    if not isinstance(colors, Mapping):
        return set()
    return {
        f"UI.colors.{name}"
        for name, value in colors.items()
        if isinstance(value, str) and _HEX_COLOR_RE.match(value)
    }


def _build_color_ref_paths(current: Mapping[str, Any]) -> set[str]:
    paths: set[str] = set()
    ui = current.get("UI") if isinstance(current, Mapping) else None
    if not isinstance(ui, Mapping):
        return paths
    tagcolors = ui.get("tagcolors")
    if isinstance(tagcolors, Mapping):
        for key in tagcolors:
            paths.add(f"UI.tagcolors.{key}")
    tsc = ui.get("torrentsStateColors")
    if isinstance(tsc, Mapping):
        for key in tsc:
            paths.add(f"UI.torrentsStateColors.{key}")
    ds = ui.get("dateStates")
    if isinstance(ds, Mapping):
        for state, body in ds.items():
            if isinstance(body, Mapping) and "color" in body:
                paths.add(f"UI.dateStates.{state}.color")
    return paths


def _build_select_sources(current: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return ``{dotted_path: [option, ...]}`` for fields that are
    semantically choices over keys configured elsewhere in the
    settings tree."""
    sources: dict[str, list[str]] = {}
    if not isinstance(current, Mapping):
        return sources

    for section_key, candidate in (
        ("file_managers", "last_fm_used"),
        ("torrent_managers", "last_tm_used"),
        ("database_managers", "last_db_used"),
    ):
        sect = current.get(section_key)
        if isinstance(sect, Mapping):
            options = sorted(
                k for k in sect.keys() if k != candidate and not k.startswith("_")
            )
            if options:
                sources[f"{section_key}.{candidate}"] = options

    media = current.get("media")
    if isinstance(media, Mapping):
        order = media.get("players_order")
        if isinstance(order, list) and order:
            sources["media.default_player"] = list(dict.fromkeys(order))

    sources["playback.video_encoder"] = [
        "auto",
        "libx264",
        "h264_nvenc",
        "h264_qsv",
        "h264_amf",
        "h264_mf",
    ]

    return sources


# ---------------------------------------------------------------------------
# Field descriptor construction
# ---------------------------------------------------------------------------


def _list_element_kind(value: list) -> str:
    """Return the homogeneous element-kind for a list, or ``mixed``."""
    if not value:
        return "str"
    if all(isinstance(v, bool) for v in value):
        return "bool"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        return "int"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
        return "float"
    if all(isinstance(v, str) for v in value):
        return "str"
    return "mixed"


def _list_value_text(value: list, elem_kind: str) -> str:
    if elem_kind == "mixed":
        return json.dumps(value, indent=2)
    return "\n".join("" if v is None else str(v) for v in value)


def _build_leaf(name: str, value: Any, ctx: dict[str, Any]) -> dict[str, Any]:
    label = _humanize(name.rsplit(".", 1)[-1])

    # Multi-choice (checkbox grid over a fixed option set).
    if name in _MULTI_CHOICE_SOURCES:
        options = ctx["multi_choice_sources"].get(name) or []
        raw_value: list[str] = []
        if isinstance(value, (list, tuple)):
            raw_value = [str(v) for v in value]
        elif isinstance(value, str) and value:
            raw_value = [value]
        selected = {str(v).upper() for v in raw_value}
        return {
            "kind": "multi_choice",
            "name": name,
            "label": label,
            "value": raw_value,
            "selected": selected,
            "options": options,
        }

    # Boolean (highest priority -- always renders as toggle).
    if isinstance(value, bool):
        return {"kind": "bool", "name": name, "label": label, "value": value}

    # Numeric leaves.
    if isinstance(value, int):
        return {"kind": "int", "name": name, "label": label, "value": value}
    if isinstance(value, float):
        return {"kind": "float", "name": name, "label": label, "value": value}

    # Constrained-choice selects (must beat the generic str branch).
    select_options = ctx["select_sources"].get(name)
    if select_options is not None and isinstance(value, str):
        return {
            "kind": "select",
            "name": name,
            "label": label,
            "value": value,
            "options": list(select_options),
        }

    # Color references (named-color selects with palette-driven swatch).
    if isinstance(value, str) and name in ctx["color_ref_paths"]:
        return {
            "kind": "color_ref",
            "name": name,
            "label": label,
            "value": value,
            "options": list(ctx["color_palette"].keys()),
            "palette": dict(ctx["color_palette"]),
        }

    # Hex color values.
    if isinstance(value, str) and name in ctx["color_hex_paths"]:
        normalized = value if _HEX_COLOR_RE.match(value) else "#000000"
        return {
            "kind": "color",
            "name": name,
            "label": label,
            "value": normalized,
        }

    # Path-shaped strings get a Browse button.
    if isinstance(value, str) and _is_path_field(name):
        return {"kind": "path", "name": name, "label": label, "value": value}

    # Lists (homogeneous scalars only, else JSON fallback).
    if isinstance(value, list):
        elem_kind = _list_element_kind(value)
        return {
            "kind": "json" if elem_kind == "mixed" else "list",
            "name": name,
            "label": label,
            "elem_kind": elem_kind,
            "value": _list_value_text(value, elem_kind),
        }

    # Generic strings (password vs text).
    if value is None:
        return {"kind": "str", "name": name, "label": label, "value": ""}
    if isinstance(value, str):
        kind = "password" if _is_password_field(name) else "str"
        return {"kind": kind, "name": name, "label": label, "value": value}

    # Unknown -> JSON fallback.
    return {
        "kind": "json",
        "name": name,
        "label": label,
        "value": json.dumps(value, indent=2),
    }


def _build_group(prefix: str, value: Any, depth: int, ctx: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        children = [
            _build_group(f"{prefix}.{k}" if prefix else k, v, depth + 1, ctx)
            for k, v in value.items()
        ]
        leaf_count = sum(1 for c in children if c["kind"] != "group")
        is_bool_only = bool(children) and all(
            c["kind"] == "bool" for c in children
        )
        return {
            "kind": "group",
            "name": prefix,
            "label": _humanize(prefix.rsplit(".", 1)[-1]) if prefix else "",
            "children": children,
            "depth": depth,
            "leaf_count": leaf_count,
            "is_bool_only": is_bool_only,
        }
    return _build_leaf(prefix, value, ctx)


def build_context(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Build the auxiliary context (palette / refs / select sources)
    consumed by the leaf builder and the template."""
    palette = _build_color_palette(settings)
    multi_sources: dict[str, list[dict[str, Any]]] = {}
    for path, provider in _MULTI_CHOICE_SOURCES.items():
        if callable(provider):
            try:
                opts = provider(settings) or []
            except Exception:  # noqa: BLE001 - best effort
                opts = []
        else:
            opts = list(provider)
        multi_sources[path] = opts
    return {
        "color_palette": palette,
        "color_hex_paths": _build_color_hex_paths(settings),
        "color_ref_paths": _build_color_ref_paths(settings),
        "select_sources": _build_select_sources(settings),
        "multi_choice_sources": multi_sources,
    }


def _seed_virtual_keys(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Return a settings copy with our managed multi-choice keys seeded.

    The settings.json schema is owned by the user; we only ever add a
    key here when it's absent so the structured form can render its
    toggle. Existing values are preserved as-is.

    ``logs.enabled_categories`` defaults to the full known category
    list so the first render shows every box ticked (no silencing).
    Once the user saves, their choice (which may be the empty list)
    becomes the persisted source of truth.
    """
    if not isinstance(settings, Mapping):
        return {}
    seeded = copy.deepcopy(dict(settings))
    logs_section = seeded.get("logs")
    if not isinstance(logs_section, dict):
        logs_section = {}
        seeded["logs"] = logs_section
    if "enabled_categories" not in logs_section:
        try:
            from . import log_buffer  # type: ignore
        except ImportError:  # pragma: no cover - packaged install
            try:
                from clients.http import log_buffer  # type: ignore
            except ImportError:
                log_buffer = None  # type: ignore
        if log_buffer is not None:
            logs_section["enabled_categories"] = list(
                log_buffer.global_buffer.known_categories()
            )
        else:
            logs_section["enabled_categories"] = []
    return seeded


def build_sections(settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build the top-level section list rendered by the settings page."""
    if not isinstance(settings, Mapping):
        return []
    settings = _seed_virtual_keys(settings)
    ctx = build_context(settings)

    keys = list(settings.keys())
    ordered = [k for k in SECTION_ORDER if k in keys]
    ordered += [k for k in keys if k not in SECTION_ORDER]

    sections: list[dict[str, Any]] = []
    for key in ordered:
        built = _build_group(key, settings[key], depth=0, ctx=ctx)
        if built.get("kind") == "group":
            node = built
        else:
            node = {
                "kind": "group",
                "name": key,
                "label": _humanize(key),
                "children": [built],
                "depth": 0,
                "leaf_count": 1,
                "is_bool_only": built.get("kind") == "bool",
            }
        meta = SECTION_META.get(key, {})
        tier = SECTION_TIERS.get(key, 2)
        node["section_label"] = meta.get("label", _humanize(key))
        node["description"] = meta.get("description", "")
        node["tier"] = tier
        node["open_by_default"] = tier == 1
        sections.append(node)
    return sections


# ---------------------------------------------------------------------------
# Form parsing (reverse path)
# ---------------------------------------------------------------------------


_MISSING = object()
_TRUE_STRINGS = frozenset({"1", "true", "yes", "on", "y", "t"})


def _get_path(root: Mapping[str, Any], dotted: str) -> Any:
    parts = dotted.split(".")
    cur: Any = root
    for p in parts:
        if not isinstance(cur, Mapping) or p not in cur:
            return _MISSING
        cur = cur[p]
    return cur


def _set_path(root: MutableMapping[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur: Any = root
    for p in parts[:-1]:
        nxt = cur.get(p) if isinstance(cur, MutableMapping) else None
        if not isinstance(nxt, MutableMapping):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _coerce_int(raw: str, fallback: int) -> int:
    raw = (raw or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        try:
            return int(float(raw))
        except ValueError:
            return fallback


def _coerce_float(raw: str, fallback: float) -> float:
    raw = (raw or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return fallback


def _coerce_bool(raw: str) -> bool:
    return (raw or "").strip().lower() in _TRUE_STRINGS


def _coerce_list(raw: str, elem_kind: str, fallback: list) -> list[Any]:
    if elem_kind == "mixed":
        text = (raw or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return list(fallback)
        return parsed if isinstance(parsed, list) else list(fallback)

    out: list[Any] = []
    for line in (raw or "").splitlines():
        token = line.strip()
        if not token:
            continue
        if elem_kind == "int":
            out.append(_coerce_int(token, 0))
        elif elem_kind == "float":
            out.append(_coerce_float(token, 0.0))
        elif elem_kind == "bool":
            out.append(_coerce_bool(token))
        else:
            out.append(token)
    return out


def _iter_form_items(form: Any):
    if hasattr(form, "multi_items"):
        return list(form.multi_items())
    if hasattr(form, "items"):
        return list(form.items())
    return []


def _form_getlist(form: Any, key: str) -> list[str]:
    if hasattr(form, "getlist"):
        return list(form.getlist(key))
    return [form[key]] if hasattr(form, "__contains__") and key in form else []


def parse_form(form: Any, current: Mapping[str, Any]) -> dict[str, Any]:
    """Build a full settings dict from a form submission.

    Returns a deep copy of ``current`` with each form-provided override
    applied. Keys absent from the form are preserved as-is. Boolean
    fields use a companion ``__bool__`` hidden marker so unchecked
    boxes round-trip as ``False`` rather than disappearing. Multi-choice
    fields use ``__multi__`` for the same reason -- unticking every
    box must persist as ``[]``, not "keep the previous list".
    """
    # Seed virtual keys so multi-choice fields whose value didn't
    # exist in the saved settings still round-trip correctly.
    current = _seed_virtual_keys(current)
    result: dict[str, Any] = copy.deepcopy(dict(current))

    bool_names = set(_form_getlist(form, "__bool__"))
    multi_names = set(_form_getlist(form, "__multi__"))
    items = _iter_form_items(form)
    keys_present = {key for key, _ in items}
    for name in bool_names:
        if _get_path(current, name) is _MISSING:
            continue
        _set_path(result, name, name in keys_present)

    # Multi-choice: collect every form value for this name into a list.
    for name in multi_names:
        if _get_path(current, name) is _MISSING:
            continue
        values = [
            v.strip()
            for v in _form_getlist(form, name)
            if isinstance(v, str) and v.strip()
        ]
        # Preserve declaration order while dropping duplicates.
        seen_set: set[str] = set()
        deduped: list[str] = []
        for v in values:
            if v not in seen_set:
                seen_set.add(v)
                deduped.append(v)
        _set_path(result, name, deduped)

    seen: set[str] = set(bool_names) | multi_names
    for key, raw in items:
        if not key or key.startswith("__"):
            continue
        if key == "settings_json":
            continue
        if key in seen:
            continue
        seen.add(key)
        original = _get_path(current, key)
        if original is _MISSING:
            continue
        if isinstance(original, bool):
            if key not in bool_names:
                _set_path(result, key, _coerce_bool(raw))
            continue
        if isinstance(original, int):
            _set_path(result, key, _coerce_int(raw, original))
            continue
        if isinstance(original, float):
            _set_path(result, key, _coerce_float(raw, original))
            continue
        if isinstance(original, list):
            elem_kind = _list_element_kind(original)
            _set_path(result, key, _coerce_list(raw, elem_kind, original))
            continue
        if isinstance(original, dict):
            continue
        if original is None or isinstance(original, str):
            _set_path(result, key, raw if raw is not None else "")
            continue
        try:
            _set_path(result, key, json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            _set_path(result, key, raw)
    return result


__all__ = [
    "SECTION_META",
    "SECTION_ORDER",
    "SECTION_TIERS",
    "build_context",
    "build_sections",
    "parse_form",
]
