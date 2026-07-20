# SubsPlease release naming vs catalog titles

Research based on Nyaa `subsplease` user uploads (July 2026) cross-checked
against the local AIRING catalog and the query planner in
`adapters/search/planner.py`.

## SubsPlease title template

SubsPlease weekly releases follow a very consistent pattern:

```text
[SubsPlease] {Show Title} - {EP} ({resolution}) [{CRC}].mkv
[SubsPlease] {Show Title} ({start}-{end}) ({resolution}) [Batch]
```

Examples from recent uploads:

| SubsPlease show segment | Notes |
|-------------------------|-------|
| `Tenkosaki` | Short nickname; not the MAL shorthand `Tenbin` |
| `Tai-Ari deshita. Ojousama wa Kakutou Game nante Shinai` | Full romanized title; `.` not `:` |
| `Grand Blue S3` | Inline season token |
| `Mushoku Tensei S3` | Same |
| `World Is Dancing` | English marketing title |
| `Let's Go Kaiki-gumi` | English with hyphen |
| `Hyakkano` | Abbreviation not present in API metadata |
| `Suterare Seijo no Isekai Gohan Tabi` | Leading words of long JP title |

## How this differs from API catalog titles

Metadata providers (MAL/AniList/Kitsu) often supply:

1. **Full romanized primary title** — usually matches SubsPlease for straightforward shows.
2. **English synonyms with colon subtitles** — e.g. `Tenkosaki: The Neat and Pretty Girl…`. Nyaa does **not** index the subtitle; only the prefix (`Tenkosaki`) matches.
3. **Alternate nicknames** — e.g. MAL `Tenbin` while SubsPlease uses `Tenkosaki`.
4. **`Season N` wording** — catalog may say `Grand Blue Season 3` while SubsPlease posts `Grand Blue S3`.

## Planner mitigations (implemented)

The query planner expands each catalog title into nyaa-friendly variants:

| Variant | Example |
|---------|---------|
| ASCII fold | `Kaiyū` → `Kaiyu` |
| Punctuation loosen | `.: ` → `. ` |
| Dehyphenate inner words | `Ojou-sama` → `Ojousama` |
| Colon prefix (1–8 words) | `Tenkosaki: …` → `Tenkosaki` |
| Hyphenated 2-word prefix | `Tai-Ari deshita.: …` → `Tai-Ari deshita` |
| Leading 4-word prefix | Long titles without a usable colon form |
| Season alias | `Season 3` → `S3` |
| Season base strip | `… 2nd Season` → base title (SubsPlease continues ep #) |

Interactive profile `max_terms` was raised from **8 → 12** so expanded variants are
less likely to be capped out when many synonyms are enabled.

## Residual gaps (cannot fully automate)

These require the nickname to exist in catalog synonyms or a manual search term:

- **Independent abbreviations** (`Hyakkano`, `Tenbin` vs `Tenkosaki`)
- **English-only SubsPlease names** when the catalog only has romanized JP
- **Compound franchise titles** (`Azur Lane - Bisoku Zenshin! S2`) when the
  catalog stores only the spin-off name

Run `scripts/analyze_subsplease_titles.py` to refresh the mismatch report; output
is written to `scripts/_search_samples/subsplease_catalog_analysis.json`.

## Recommended manual fallback

When SubsPlease uses a known nickname missing from metadata, add it under
**Search options → Custom search terms** on the anime detail page.
