import { describe, expect, it } from "vitest";
import { buildSections } from "@/lib/settings-form";

describe("buildSections", () => {
  it("wraps scalar top-level keys in a group with children", () => {
    const settings = {
      last_fm_used: "Local",
      last_tm_used: "LibTorrent",
      file_managers: {
        last_fm_used: "Local",
        Local: { dataPath: "/anime" },
      },
      torrent_managers: {
        last_tm_used: "LibTorrent",
        LibTorrent: { download_path: "/torrents" },
      },
    };

    const sections = buildSections(settings, { logCategories: ["HTTP", "CLIENT"] });

    expect(sections.length).toBeGreaterThan(0);
    for (const section of sections) {
      expect(Array.isArray(section.children)).toBe(true);
    }

    const fmSection = sections.find((s) => s.name === "last_fm_used");
    expect(fmSection).toBeDefined();
    expect(fmSection?.children).toHaveLength(1);
    expect(fmSection?.children[0]?.kind).toBe("str");
    expect(fmSection?.children[0]?.name).toBe("last_fm_used");

    const tmSection = sections.find((s) => s.name === "last_tm_used");
    expect(tmSection).toBeDefined();
    expect(tmSection?.children).toHaveLength(1);
    expect(tmSection?.children[0]?.kind).toBe("str");
  });

  it("keeps object top-level keys as groups unchanged", () => {
    const settings = {
      anime: { animePerPage: 48, hideRated: true },
    };

    const sections = buildSections(settings);
    const anime = sections.find((s) => s.name === "anime");

    expect(anime?.kind).toBe("group");
    expect(anime?.children.length).toBeGreaterThan(0);
  });
});
