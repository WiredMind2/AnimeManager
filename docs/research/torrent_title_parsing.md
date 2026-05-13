# Torrent title parsing — naming conventions report

> **Status:** research / pre-design — feeds the upcoming "filter torrent
> search results" feature in the torrent search UI.
>
> **Data source:** `scripts/run_search_samples.py` collected **4 220 raw
> torrent rows** across **6 anime queries** (One Piece, Frieren, Bocchi the
> Rock, Demon Slayer, Spy x Family, Jujutsu Kaisen) through the existing
> `SearchFacade` / nova3 pipeline. The full dataset is checked in under
> `scripts/_search_samples/*.json`; the aggregated stats live in
> `scripts/_search_samples/_analysis.json`.
>
> **Analyzer:** `scripts/analyze_naming.py` (+ ad-hoc `scripts/sample_inspect.py`).

This document is the deliverable for the *first* phase of the feature:
*"Start by running various torrent searches and create a report on the
different naming conventions found, and how we could parse them
automatically."* It contains:

1. Why we need parsing.
2. What the corpus actually looks like (numbers, distributions, edge cases).
3. A proposed parsing pipeline and the regexes that back it.
4. A proposed data model exposed to the UI/filtering layer.
5. Implementation plan (incremental, behind a feature flag).

---

## 1. Motivation

Today `clients/http/templates/partials/anime_torrent_row.html` shows the
raw title only (`{{ row.name }}`), plus size / seeds / leech. The user
asked for a way to *filter* the result list by:

| Facet      | Examples                                              |
|------------|-------------------------------------------------------|
| Publisher  | `SubsPlease`, `Erai-raws`, `Judas`, `ToonsHub`, `ASW` |
| Quality    | `1080p`, `720p`, `2160p`, `BD`/`WEB-DL`, `HEVC`/`AVC` |
| Season     | `S1`, `S2`, `Season 3`, `Part II`, `Cour 2`           |
| Episode    | `01`, `EP12`, `S03E12`, `Episode 7`, `01-12` (batch)  |

To do this client-side or server-side filtering we have to turn the
free-form `name` column produced by nova3 into a small structured record.

## 2. Corpus snapshot

The numbers below are taken verbatim from
`scripts/_search_samples/_analysis.json` (n = 4 220 rows after dedupe by
the existing pipeline).

### 2.1 Publishers / release groups

* **84 %** of rows expose the publisher as a leading **square bracket**:
  `[SubsPlease] One Piece - 1161 (1080p) [9BEAE717].mkv`.
* **~4 %** use a **trailing dash tag**, scene-style, e.g.
  `Bocchi.the.Rock.S01.1080p.BluRay.10-Bit.FLAC2.0.x265-YURASUKA`
  (publisher = `YURASUKA`). 173 rows in the corpus match this pattern.
* **~1.3 %** are Chinese / Japanese fansubs using the angle-style
  bracket `【...】`, e.g. `【喵萌奶茶屋】★10月新番★[孤独摇滚!...]`. 56 rows.
* The remaining **~16 %** (671 rows) lack a clear publisher token. These
  are mostly fan re-encodes (`...-realpinkgirl321`) and bare scene
  filenames where the encoder is embedded somewhere in the middle.

Top 10 publishers across all queries (head-bracket only):

| Publisher        | Hits |
|------------------|-----:|
| SubsPlease       | 581  |
| Erai-raws        | 469  |
| ToonsHub         | 315  |
| Yameii           | 172  |
| ASW              | 128  |
| Judas            | 125  |
| Ember            | 118  |
| ANi              |  83  |
| LostYears        |  78  |
| Anime Time       |  74  |

The long tail (DKB, Shincaps, NC-Raws, NanakoRaws, Kaerizaki-Fansub,
Tsundere-Raws, …) shows that we **cannot maintain a closed allow-list**
of publishers; the parser must accept any plausible bracketed/tail token
and then *bucket* low-frequency ones in the UI.

#### Pitfalls

* **CRC suffix `[XXXXXXXX]`** – 1 217 rows end with an 8-char hex CRC
  bracket. We must explicitly skip those when reading tail brackets.
* **Multi-bracket titles** – 1 838 rows have ≥3 bracket pairs
  (`[Pub] Title [1080p][HEVC 10bit x265][AAC][Multi Sub]`). The parser
  must read the *first* bracket as the publisher and treat the rest as
  metadata.
* **Hyphenated names** – `Erai-raws`, `Tsundere-Raws`, `NC-Raws`,
  `New-raws`, `Anime-Chap`. The regex needs to allow `[A-Za-z0-9._-]`
  inside the publisher token.

### 2.2 Quality

#### Resolution

| Token       |  Hits |
|-------------|------:|
| `1080p`     | 3 259 |
| `720p`      |   436 |
| `480p`      |   131 |
| `1920x1080` |   111 |
| `2160p`     |    93 |
| `1440x1080` |    39 |
| `1280x720`  |    25 |
| `4k`/`UHD`  |    14 |

Lesson: we should canonicalise to the `XXXXp` form. `2160p` and `4k`/`UHD`
should both be reported as the `2160p` filter value.

#### Source

CR (Crunchyroll) dominates with 826 rows, followed by generic `WEB`
(510), `WEBRip` (305), `WEB-DL` (218), `BD`/`BluRay` (203 combined),
`AMZN` (125), `NF` (Netflix, 111), and a long tail of regional
streaming services (`HiDIVE`, `BILI`, `iQ`, `TVER`, `ABEMA`, `DSNP`).
We must normalise variants: `WEB-DL` ≡ `WEBDL` ≡ `WEB-Rip` ≡ `WEBRip`
≡ `WEB`, `BluRay` ≡ `BD` ≡ `BDRip` ≡ `BDRemux` ≡ `BDMV`. Streaming
services should be exposed as a secondary "Provider" facet.

#### Codec

| Token         | Hits | Canonical |
|---------------|-----:|-----------|
| `HEVC`        |  893 | H.265     |
| `H.264`/`H264`|  560 | H.264     |
| `x264`        |  502 | H.264     |
| `AVC`         |  391 | H.264     |
| `x265`        |  191 | H.265     |
| `AV1`         |   95 | AV1       |
| `H.265`/`H265`|   60 | H.265     |
| `VP9`         |   12 | VP9       |

We **must** unify these into a single `Codec` enum
(`H264 | H265 | AV1 | VP9 | OTHER`); 1 053 rows (x264 + AVC + H264 +
H.264) are H.264 today but only one of those four tokens will match a
naive substring filter.

#### Audio / bit-depth / dual-audio

* `AAC` and variants account for the vast majority of audio tokens
  (1 329 + 432 + 130).
* `10-bit` / `10bit` appears in 76 rows.
* `Dual-Audio` / `Multi-Audio` / `Multi-Subs` appears in ~9 % of titles.

### 2.3 Season

Total rows with a detectable season: **2 052 / 4 220 (49 %)** — the rest
are batches, movies, or episode-only releases.

| Pattern (regex)                 | Hits |
|---------------------------------|-----:|
| `\bS(\d{1,2})(?:E\d{1,3})?\b`   | 1 731 |
| `\bSeason[\s._-]*(\d{1,2})\b`   |   297 |
| `\b(?:Part|Cour)[\s._-]*([0-9IVX]{1,3})\b` | 24 |

Edge cases observed:

* `Season 01 (S01) V2` — both `Season N` and `Sxx` present; pick the
  numeric Sxx form (highest confidence).
* `(SS3)` — a few publishers (e.g. Fumi-Raws Demon Slayer Swordsmith
  Village) write `(SS3)` instead of `S3`. We can tolerate this with
  `\bSS?(\d{1,2})\b`.
* Recap-only releases like `BOCCHI THE ROCK S06E00 ... Recap Part 1` —
  technically the publisher tags it `S06`; we should accept what the
  release says and not try to "correct" it.

### 2.4 Episode

Total rows with a detectable episode: **2 859 / 4 220 (68 %)**. The rest
are season packs / batches / movies (see §2.5).

| Pattern          | Hits  | Example token |
|------------------|------:|---------------|
| `SxxExx`         | 1 417 | `S03E12`      |
| `- xx ` (Subs/Erai style) | 1 412 | ` - 1161 ` |
| `Exx`            |    12 | `E04`         |
| `Episode xx`     |     8 | `Episode 07`  |
| `xx of yy`       |     5 | `08 of 08`    |
| `EPxxx`          |     4 | `EP1161`      |

> **Caveat:** the `- xx ` form is a strong false-positive magnet — it
> happily matches movie year numbers (`- 2024 `) or random integers.
> The production parser must:
>
> 1. only accept this pattern *after* the title proper (i.e. after the
>    leading bracket if any) and *before* the first metadata token
>    (`(1080p)`, `[HEVC...]`, …);
> 2. cap the captured number at 3 digits and reject obvious year
>    candidates (1900 ≤ n ≤ current_year + 5) when paired with no other
>    episode signal.

### 2.5 Batches / season packs / movies

195 rows look like a multi-episode release. Indicators we detect:

* Episode range: `(01-12)`, `01 ~ 12`, `001-1071`, `[01-12 + SPs]`.
* Keyword: `Batch`, `Complete`, `Season Pack`, `BD-Box`.
* Combination: `(Season 01) [Batch]`, `[Trix] ... (Batch)`.

For filtering we want a tri-state `EpisodeKind` enum:
`SINGLE | RANGE(start,end) | UNKNOWN`. A range result with
`start == end` collapses to `SINGLE`.

### 2.6 Other useful signals we should expose

| Signal           | How to detect                                | Value to filter |
|------------------|----------------------------------------------|-----------------|
| Language / subs  | `MULTi`, `VOSTFR`, `VF`, `Multi-Sub(s)`, `Eng-Sub`, `Dual-Audio`, `RUS+JAP`, `简体`, `繁體` | UI badge / language filter |
| Bit depth        | `10-bit`, `10bit`, `8bit`                    | quality filter  |
| File extension   | `.mkv`, `.mp4`, `.avi`                       | informational   |
| CRC checksum     | `[XXXXXXXX]` 8-hex at the tail               | strip pre-parse |
| Year             | `\b(19|20)\d{2}\b`                           | informational   |

## 3. Proposed parsing pipeline

A four-stage pipeline keeps each step independently testable. Pseudo
order on the *normalized* title:

```
RAW  →  strip_extension  →  strip_crc  →  detect_publisher
     →  detect_quality   →  detect_season_episode  →  detect_batch
     →  ParsedTitle
```

### 3.1 Normalisation

1. Unicode NFKC + control-character strip (already done in
   `adapters/search/parser.py::ResultParser._clean_text`).
2. Replace runs of `.` / `_` with spaces **only for matching**, never
   for the displayed name. This lets the same regexes hit both
   `[SubsPlease] One Piece - 1161 (1080p) [9BEAE717].mkv` and
   `Bocchi.the.Rock.S01.1080p.BluRay.x265-YURASUKA`.
3. Strip the trailing `.mkv` / `.mp4` / `.avi` from the working copy.
4. Strip the trailing CRC `[XXXXXXXX]` (regex
   `r"\s*\[[0-9A-Fa-f]{8}\]\s*$"`) from the working copy.

### 3.2 Publisher detection (priority order)

```
1. ^\s*\[(?P<pub>[^\]]{1,40})\]                      # [SubsPlease] / [Erai-raws] / [Anime Time]
2. ^\s*【(?P<pub>[^】]{1,40})】                       # CJK fansubs
3. -(?P<pub>[A-Za-z][\w.-]{2,30})                    # tail dash, applied AFTER stripping
   (after stripping CRC + extension + parenthetical metadata)
4. else publisher = None  (UI bucket = "Other / unknown")
```

Guardrails for rule 3: the candidate must not match a known metadata
vocabulary (`x264|x265|H264|H265|HEVC|AVC|1080p|10bit|…`). We will
maintain that vocabulary as a constant in
`adapters/search/title_parser.py` and use it as a *negative* filter.

### 3.3 Quality detection

* `resolution = first hit of`
  `r"(?<![\w])(?:\d{3,4}p|\d{3,4}x\d{3,4}|4k|UHD)(?![\w])"`,
  canonicalised to `XXXXp` (`4k`/`UHD` → `2160p`, `1920x1080` → `1080p`,
  `1280x720` → `720p`, `1440x1080` → `1080p (anamorphic)`).
* `source` = first match of the source vocabulary, normalised to a small
  enum: `BLURAY | WEB-DL | WEBRIP | HDTV | DVD | TVRIP | OTHER`. A
  separate `provider` field captures CR/AMZN/NF/FUNI/HIDIVE/BILI/iQ/etc.
* `codec` = enum `H264 | H265 | AV1 | VP9 | OTHER`, derived from the
  alias table above.
* `bit_depth ∈ {8, 10, None}` from `10[- ]?bit` / `8[- ]?bit`.
* `audio` = first match of the audio vocabulary, presented unmodified
  in the UI (lower filtering priority).

### 3.4 Season detection (priority order)

```
1. \bSS?(?P<s>\d{1,2})(?:E\d{1,3})?\b        # S1, S03, S03E12, SS3
2. \bSeason[\s._-]*(?P<s>\d{1,2})\b
3. \b(?:Part|Cour)[\s._-]*(?P<s>[0-9IVX]{1,3})\b   # Part II, Cour 2
```

Conflict resolution: if more than one pattern matches, prefer rule 1
(it is the most explicit). Roman numerals are mapped to integers via a
tiny table (`I=1 … X=10`).

### 3.5 Episode detection (priority order)

```
1. \bS\d{1,2}E(?P<e>\d{1,3})\b               # SxxExx
2. \bEP[\s._-]?(?P<e>\d{1,4})\b              # EP1161
3. \bE(?P<e>\d{2,3})\b                        # bare E04 (require >=2 digits to avoid false hits)
4. \bEpisode[\s._-]+(?P<e>\d{1,3})\b
5. ` - (?P<e>\d{1,4})(?:v\d)? `              # SubsPlease/Erai style — guarded by §2.4
6. \((?P<start>\d{1,3})\s*[-~]\s*(?P<end>\d{1,3})\)   # range "(01-12)"
   or  \b(?P<start>\d{1,3})\s*~\s*(?P<end>\d{1,3})\b
   or  \b(?P<start>\d{1,3})\s+of\s+(?P<end>\d{1,3})\b
```

Rules 1–5 give a single episode → `EpisodeKind.SINGLE`. Rule 6 gives a
range → `EpisodeKind.RANGE`. A title with no episode signal but a
batch keyword (`Batch`, `Complete`, `Season Pack`, `BD-Box`) is reported
as `RANGE(None, None)` (an "unbounded batch").

## 4. Proposed data model

```python
@dataclass(frozen=True)
class ParsedTitle:
    raw: str                       # original name, untouched
    publisher: str | None          # canonicalised lower-case key
    publisher_display: str | None  # the bracketed text as displayed
    publisher_source: Literal["head_bracket", "cjk_bracket",
                              "tail_dash", "none"]

    resolution: str | None         # "2160p" | "1080p" | "720p" | "480p" | ...
    source: Source | None          # enum: BLURAY / WEB-DL / WEBRIP / HDTV / DVD / TVRIP
    provider: str | None           # "CR" / "AMZN" / "NF" / "FUNi" / ...
    codec: Codec | None            # enum: H264 / H265 / AV1 / VP9 / OTHER
    bit_depth: int | None          # 8 / 10
    audio: str | None              # "FLAC" / "AAC2.0" / ...

    season: int | None             # 1, 2, ...
    season_source: Literal["sxx", "season_word", "part_cour", "none"]

    episode_kind: EpisodeKind      # SINGLE / RANGE / NONE
    episode: int | None            # filled when episode_kind=SINGLE
    episode_start: int | None      # filled when episode_kind=RANGE
    episode_end: int | None        # filled when episode_kind=RANGE

    is_batch: bool                 # any "Batch"/"Complete" keyword OR RANGE
    languages: tuple[str, ...]     # ("multi-sub", "dual-audio", "vostfr", ...)
    crc: str | None                # 8-hex CRC if present at the tail
    extension: str | None          # ".mkv" / ".mp4" if present
    year: int | None               # 4-digit year if found

    parse_confidence: float        # 0.0..1.0 — share of facets resolved
```

`parse_confidence` is the proportion of the four "headline" facets
(publisher / resolution / season / episode) that were resolved. The UI
can grey out rows with confidence < 0.25 and still let the user
"force" them to display.

## 5. Implementation plan

### Phase A — Parser (no UI yet)

1. **New module:** `adapters/search/title_parser.py`
   * `parse_title(name: str) -> ParsedTitle`
   * vocabulary constants for sources, providers, codecs, languages.
2. **Integrate into the pipeline:** in `adapters/search/parser.py` the
   `ResultParser.parse` method calls `parse_title(name)` and adds the
   resulting `ParsedTitle` to `TorrentResult` (new optional field,
   default `None` so legacy callers keep working). `TorrentResult.as_dict`
   gains a `"parsed"` sub-dict.
3. **Unit tests:** `tests/unit/adapters/search/test_title_parser.py`,
   seeded with the >100 hand-picked examples already collected in
   `scripts/_search_samples/_analysis.json` ("examples_by_pattern"
   and the "no_publisher" / "no_episode" tails). Each example becomes a
   parametrised case asserting the expected facet values.

   Acceptance goal for Phase A:
   * publisher recall ≥ 90 % on the corpus (currently 84 % head bracket
     only),
   * episode recall ≥ 90 % for *single-episode* titles (currently 68 %
     when batches are not excluded; the batch detector should account
     for most of the gap),
   * 0 false positives for `Sxx` season in titles that say
     "(Season 1)" only, etc.

### Phase B — SDK surface

`ClientSDK.search_torrents` / `ClientSDK.stream_torrents` already returns
a dict per row. We expand the dict with a `parsed` sub-object that the
HTML layer will use as-is. No change to the streaming-row HTMX wire
format other than the additional fields.

### Phase C — Filter UI (HTTP client)

1. Update `clients/http/templates/partials/anime_torrent_results.html`
   to render a top filter row (already styled like `filter_chips.html`),
   plus 4 dropdowns:
   * Publisher (auto-populated from the streamed results)
   * Quality (resolution + codec combos collapsed: e.g.
     "1080p H.265", "1080p H.264", "720p H.265", "4k")
   * Season (auto-populated)
   * Episode kind: All / Single episode / Batch
2. Filtering is **client-side** (the rows are already in the DOM via
   SSE). Each `<tr>` gets `data-pub`, `data-res`, `data-codec`,
   `data-season`, `data-ep`, `data-batch` attributes. Static JS
   (`clients/http/static/js/app.js`) reads those and toggles
   `display:none` based on the active filters.
3. Update `clients/http/templates/partials/anime_torrent_row.html` to
   surface a compact metadata strip ("[SubsPlease] · 1080p · S1E12 ·
   CR · H.264") under the raw title, mirroring how trackers like
   Sonarr display releases.

### Phase D — Multi-term planning ("run multiple searches")

The torrent searches we ran already fan out across every enabled
nyaa-style engine (`adapters/search/engine_policy.json`); the
heterogeneity comes from those engines, not from extra queries. The
parsing layer is what unifies them, so multi-engine fan-out + good
parsing is the right combination.

For anime that publish under multiple romanisations (e.g. "Demon Slayer"
vs "Kimetsu no Yaiba"), the SDK already supports per-anime saved
`search_terms` via `clients/http/web.py::web_anime_torrent_search`. Once
the parser lands we can additionally:

* persist `parsed.publisher` next to each saved term so a future
  "include only SubsPlease" recipe sticks,
* and offer an "expand query with alt titles" toggle that pulls
  alternative titles from the anime metadata and submits them as
  additional search terms (the planner already caps at
  `max_terms=8`).

That work belongs in Phase E and is out of scope for the parsing
research deliverable.

## 6. Risks / open questions

* **Year vs episode collisions** — Movies titled with a year (`Demon
  Slayer Kimetsu No Yaiba Infinity Castle 2025 1080p WEB-DL ...`) can
  fool the `- xx ` and `Exx` rules. The proposed guard (reject 4-digit
  years when paired with a "Movie" keyword or no season signal) covers
  the cases we see in the corpus, but the regression suite should
  encode them.
* **Long-tail Chinese fansubs** — 56 rows in our sample use `【...】`
  publishers; some of those also encode the show name and episode in
  Chinese. We will surface the publisher, but episode extraction may
  fail more often on this subset. The UI should not drop those rows;
  it should mark them as "metadata incomplete" so power users can
  still see them.
* **False-positive publishers from tail-dash** — Some rows end with
  `-Tsundere-Raws (CR)` where the parenthetical confuses the trailing
  regex. The implementation must skip parenthetical metadata before
  applying rule 3.
* **Resolution canonicalisation** — `1440x1080` is anamorphic 1080p;
  collapsing it to `1080p` loses information. We will tag the
  resolution with an `anamorphic: True` flag instead of dropping the
  distinction.

## 7. Next concrete actions

1. Land the parser module + unit tests (Phase A) — small PR, no UI
   change visible to users.
2. Wire `parse_title` into `ResultParser.parse` + extend the streamed
   row JSON (Phase B). HTMX consumers keep working because all new
   fields are additive.
3. Ship the filter chips on the torrent search panel (Phase C).
4. Iterate on alt-title query expansion only after Phase C is in users'
   hands.

---

### Appendix A — files referenced

| Path                                              | Purpose                          |
|---------------------------------------------------|----------------------------------|
| `scripts/run_search_samples.py`                   | Re-runs the fan-out search       |
| `scripts/analyze_naming.py`                       | Bucketed regex statistics        |
| `scripts/sample_inspect.py`                       | Spot-checks (CJK / tail / Scene) |
| `scripts/_search_samples/*.json`                  | Raw torrent rows per query       |
| `scripts/_search_samples/_analysis.json`          | Aggregated counters              |
| `adapters/search/parser.py`                       | Where `parse_title` will plug in |
| `clients/http/templates/partials/anime_torrent_*` | UI surface for the filter chips  |
