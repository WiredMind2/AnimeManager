import re
from datetime import datetime, timezone

import requests

from shared.utils.broadcast_schedule import (
    broadcast_slot_to_string,
    utc_timestamp_to_jst_slot,
)

try:
    from .APIUtils import Anime, APIUtils, Character, EnhancedSession
except ImportError:
    from APIUtils import Anime, APIUtils, Character, EnhancedSession


def _current_anilist_season() -> tuple[int, str]:
    """Return ``(seasonYear, MediaSeason)`` for the current anime season."""
    now = datetime.now(timezone.utc)
    month = now.month
    if month <= 3:
        season = "WINTER"
    elif month <= 6:
        season = "SPRING"
    elif month <= 9:
        season = "SUMMER"
    else:
        season = "FALL"
    return now.year, season


def _anilist_season_enum(season: str) -> str | None:
    normalized = str(season or "").strip().lower()
    mapping = {
        "winter": "WINTER",
        "spring": "SPRING",
        "summer": "SUMMER",
        "fall": "FALL",
    }
    return mapping.get(normalized)


class QueryObject:
    def __init__(self, name, args=None, fields=None) -> None:
        self.name = name
        self.args = args or []  # [(name, ?type, ?value)]
        self.fields = set(fields or [])

    def __str__(self):
        return self.build()

    def set_arg(self, arg):
        for i, sub_arg in enumerate(self.args):
            if sub_arg[0] == arg[0]:
                # Same name
                self.args[i] = arg
                break
        else:
            self.args.append(arg)

    def add_field(self, field):
        self.fields.add(field)
        return self

    def del_field(self, field):
        if field in self.fields:
            self.fields.remove(field)
        return self

    def build(self):
        args = []
        for arg, arg_type, *value in self.args:
            text = f"{arg}: {arg_type}"
            if value:
                value = value[0]
                if isinstance(value, str):
                    value = f'"{value}"'
                text += f" = {value}"
            args.append(text)

        text = [self.name]

        if args:
            text.append(f'({", ".join(args)})')

        if self.fields:
            text.append("{")

            for field in self.fields:
                text.append(str(field))

            text.append("}")

        return " ".join(text)


class AnilistCoWrapper(APIUtils):
    def __init__(self):
        super().__init__()
        self.session = EnhancedSession(timeout=30)
        self.url = "https://graphql.anilist.co"
        self.apiKey = "anilist_id"

        self.media_fields = [
            "id",
            "idMal",
            QueryObject(
                "title",
                fields=[
                    "romaji",
                    "english",
                    "native",
                ],
            ),
            QueryObject("status", args=(("version", 2),)),
            QueryObject("description", args=(("asHtml", "false"),)),
            QueryObject(
                "startDate",
                fields=[
                    "year",
                    "month",
                    "day",
                ],
            ),
            QueryObject(
                "endDate",
                fields=[
                    "year",
                    "month",
                    "day",
                ],
            ),
            "episodes",
            "duration",
            QueryObject(
                "trailer",
                fields=[
                    "site",
                ],
            ),
            QueryObject(
                "coverImage",
                fields=[
                    "extraLarge",
                    "large",
                    "medium",
                ],
            ),
            "genres",
            "synonyms",
            QueryObject(
                "tags",
                fields=[
                    "id",
                    "name",
                    "description",
                    "isAdult",
                ],
            ),
            # QueryObject(
            # 	'relations',
            # 	fields=[
            # 		QueryObject(
            # 			'edges',
            # 			fields=[
            # 				'relationType',
            # 				QueryObject(
            # 					'node',
            # 					fields=[
            # 						'id',
            # 						QueryObject(
            # 							'title',
            # 							fields=[
            # 								'english',
            # 							]
            # 						),
            # 						'type',
            # 					]
            # 				),
            # 			]
            # 		),
            # 	]
            # ),
            # QueryObject(
            # 	'characters',
            # 	fields=[
            # 		QueryObject(
            # 			'edges',
            # 			fields=[
            # 				'role',
            # 				QueryObject(
            # 					'node',
            # 					fields=[
            # 						'id',
            # 						QueryObject(
            # 							'name',
            # 							fields=[
            # 								'full',
            # 							]
            # 						),
            # 						QueryObject(
            # 							'image',
            # 							fields=[
            # 								'large',
            # 								'medium',
            # 							]
            # 						),
            # 						'description',
            # 					]
            # 				),
            # 			]
            # 		),
            # 	]
            # ),
            "isAdult",
            QueryObject(
                "nextAiringEpisode",
                fields=[
                    "airingAt",
                ],
            ),
        ]

        self.media_query = QueryObject(
            "Media",
            args=(
                ("id", "$id"),
                ("type", "ANIME"),
            ),
            fields=self.media_fields,
        )

        self.pagination_query = QueryObject(
            # query ($id: Int, $page: Int, $perPage: Int, $search: String) {
            "Page",
            args=(
                ("page", "$page"),
                ("perPage", "$perPage"),
            ),
            fields=[
                QueryObject(
                    "pageInfo",
                    fields=[
                        "total",
                        "currentPage",
                        "lastPage",
                        "hasNextPage",
                        "perPage",
                    ],
                )
            ],
        )

    def anime(self, id):
        ani_id = self.getId(id)
        if ani_id is None:
            return None

        query = QueryObject("query", args=(("$id", "Int"),), fields=[self.media_query])

        variables = {"id": ani_id}
        try:
            if hasattr(self, "session") and self.session is not None:
                rep = self.session.request(
                    "POST", self.url, json={"query": str(query), "variables": variables}
                )
            else:
                rep = requests.post(
                    self.url, json={"query": str(query), "variables": variables}
                )
        except Exception as e:
            self.log("ANILIST", "Network error during anime():", e)
            return None

        try:
            data = rep.json().get("data")
        except Exception as e:
            self.log("ANILIST", "Invalid JSON response from Anilist:", e)
            return None

        if not data:
            return None

        anime = self._convertAnime(data.get("Media"))
        return anime

    def animeCharacters(self, id):
        """AniList does not expose a character endpoint in this wrapper."""
        return []

    def searchAnime(self, search, limit=50):
        query = QueryObject(
            "query",
            args=(
                ("$id", "Int"),
                ("$page", "Int"),
                ("$perPage", "Int"),
                ("$search", "String"),
            ),
            fields=[
                self.pagination_query.add_field(
                    QueryObject(
                        "media",
                        args=(
                            ("id", "$id"),
                            ("search", "$search"),
                        ),
                        fields=self.media_fields,
                    )
                )
            ],
        )

        variables = {"search": search, "page": 1, "perPage": 50}

        count = 0
        for a in self.iterate(query, variables):
            data = self._convertAnime(a)
            if data and len(data) != 0:
                yield data
                count += 1
                if count >= limit:
                    return

    def season(self, year, season, limit=50):
        season_enum = _anilist_season_enum(season)
        if season_enum is None:
            return
        query = QueryObject(
            "query",
            args=(
                ("$page", "Int"),
                ("$perPage", "Int"),
                ("$season", "MediaSeason"),
                ("$seasonYear", "Int"),
            ),
            fields=[
                self.pagination_query.add_field(
                    QueryObject(
                        "media",
                        args=(
                            ("season", "$season"),
                            ("seasonYear", "$seasonYear"),
                            ("type", "ANIME"),
                            ("sort", "START_DATE_DESC"),
                        ),
                        fields=self.media_fields,
                    )
                )
            ],
        )
        variables = {
            "page": 1,
            "perPage": min(50, max(1, int(limit))),
            "season": season_enum,
            "seasonYear": int(year),
            "max_pages": max(1, (int(limit) + 49) // 50),
        }
        count = 0
        for media in self.iterate(query, variables):
            data = self._convertAnime(media)
            if data and len(data) != 0:
                yield data
                count += 1
                if count >= limit:
                    return

    def genre(self, name, limit=50):
        query = QueryObject(
            "query",
            args=(
                ("$page", "Int"),
                ("$perPage", "Int"),
                ("$genre", "String"),
            ),
            fields=[
                self.pagination_query.add_field(
                    QueryObject(
                        "media",
                        args=(
                            ("genre_in", "[$genre]"),
                            ("type", "ANIME"),
                            ("sort", "POPULARITY_DESC"),
                        ),
                        fields=self.media_fields,
                    )
                )
            ],
        )
        variables = {
            "page": 1,
            "perPage": min(50, max(1, int(limit))),
            "genre": str(name),
            "max_pages": max(1, (int(limit) + 49) // 50),
        }
        count = 0
        for media in self.iterate(query, variables):
            data = self._convertAnime(media)
            if data and len(data) != 0:
                yield data
                count += 1
                if count >= limit:
                    return

    def schedule(self, limit=50):
        season_year, season = _current_anilist_season()
        query = QueryObject(
            "query",
            args=(
                ("$page", "Int"),
                ("$perPage", "Int"),
                ("$season", "MediaSeason"),
                ("$seasonYear", "Int"),
            ),
            fields=[
                self.pagination_query.add_field(
                    QueryObject(
                        "media",
                        args=(
                            ("season", "$season"),
                            ("seasonYear", "$seasonYear"),
                            ("type", "ANIME"),
                            ("sort", "START_DATE_DESC"),
                        ),
                        fields=self.media_fields,
                    )
                )
            ],
        )
        variables = {
            "page": 1,
            "perPage": min(50, max(1, int(limit))),
            "season": season,
            "seasonYear": int(season_year),
            "max_pages": max(1, (int(limit) + 49) // 50),
        }
        count = 0
        for media in self.iterate(query, variables):
            data = self._convertAnime(media)
            if data and len(data) != 0:
                yield data
                count += 1
                if count >= limit:
                    return

    def _convertAnime(self, a):
        if a is None:
            return
        external_ids = {"anilist_id": int(a.get("id"))}
        mal_id = a.get("mal_id") or a.get("idMal")
        if mal_id:
            external_ids["mal_id"] = int(mal_id)
        if getattr(self, "schedule_light", False):
            out = Anime()
            out._schedule_external_ids = external_ids

            keys = ["english", "romaji", "native"]
            titles = []
            for key in keys:
                title = a.get("title").get(key)
                if title:
                    titles.append(title)
            titles += a.get("synonyms", [])
            out.title = titles[0].rstrip(".") if titles else ""
            out.title_synonyms = titles

            mapped_status = {
                "FINISHED": "FINISHED",
                "RELEASING": "AIRING",
                "NOT_YET_RELEASED": "UPCOMING",
                "CANCELLED": "UNKNOWN",
                "HIATUS": "UPCOMING",
            }
            out.status = mapped_status.get(a.get("status"))

            desc = a.get("description")
            if desc:
                out.synopsis = re.sub("<.*?>", "", desc)
            else:
                out.synopsis = None

            datefrom = a.get("startDate")
            if datefrom and None not in datefrom.values():
                try:
                    dt = datetime(**datefrom)
                    out.date_from = int(dt.replace(tzinfo=timezone.utc).timestamp())
                except Exception:
                    out.date_from = None
            else:
                out.date_from = None

            dateto = a.get("endDate")
            if dateto and None not in dateto.values():
                try:
                    dt = datetime(**dateto)
                    out.date_to = int(dt.replace(tzinfo=timezone.utc).timestamp())
                except Exception:
                    out.date_to = None
            else:
                out.date_to = None

            out.episodes = a.get("episodes")
            out.duration = a.get("duration")
            out.trailer = (a.get("trailer") or {}).get("site")
            out.rating = "R" if a.get("isAdult") else ""
            out.picture = a.get("coverImage", {}).get("medium")
            broadcast = (a.get("nextAiringEpisode") or {}).get("airingAt")
            if broadcast:
                slot = utc_timestamp_to_jst_slot(int(broadcast))
                out.broadcast = broadcast_slot_to_string(slot)
            out.status = self.getStatus(out)
            return out

        id = self.resolve_catalog_id(external_ids)
        out = Anime()

        out.id = id

        keys = ["english", "romaji", "native"]
        titles = []
        for key in keys:
            title = a.get("title").get(key)
            if title:
                titles.append(title)

        titles += a.get("synonyms", [])

        # Every anime should have at least one title
        out.title = titles[0].rstrip(".")
        # rstrip() is a fix for a problem where files would get corrupted

        out.title_synonyms = titles

        mapped_status = {
            "FINISHED": "FINISHED",
            "RELEASING": "AIRING",
            "NOT_YET_RELEASED": "UPCOMING",
            "CANCELLED": "UNKNOWN",
            "HIATUS": "UPCOMING",
        }
        out.status = mapped_status.get(a.get("status"))

        desc = a.get("description")
        if desc:  # Avoid using regex when it isn't necessary
            out.synopsis = re.sub("<.*?>", "", desc)  # Remove all HTML tags
        else:
            out.synopsis = None

        datefrom = a.get("startDate")
        if None not in datefrom.values():
            try:
                dt = datetime(**datefrom)
                out.date_from = int(dt.replace(tzinfo=timezone.utc).timestamp())
            except Exception:
                out.date_from = None
        else:
            out.date_from = None

        dateto = a.get("endDate")

        if None not in dateto.values():
            try:
                try:
                    dt = datetime(**dateto)
                    out.date_to = int(dt.replace(tzinfo=timezone.utc).timestamp())
                except Exception:
                    out.date_to = None
            except:
                # Probably ValueError for an invalid date (like https://anilist.co/manga/81583/34sai-Mushokusan)
                out.date_to = None
        else:
            out.date_to = None

        out.episodes = a.get("episodes")
        out.duration = a.get("duration")
        out.trailer = (a.get("trailer") or {}).get("site")
        out.rating = "R" if a.get("isAdult") else ""

        out.picture = a.get("coverImage", {}).get("medium")

        pictures = []

        sizes = {"large": "medium", "medium": "small", "extraLarge": "large"}
        pictures = []
        for key, size in sizes.items():
            url = a.get("coverImage", {}).get(key)
            if url:
                img = {"url": url, "size": size}
                pictures.append(img)

        self.save_pictures(id, pictures)

        broadcast = (a.get("nextAiringEpisode") or {}).get("airingAt")
        if broadcast:
            slot = utc_timestamp_to_jst_slot(int(broadcast))
            self.save_broadcast(id, slot.weekday, slot.hour, slot.minute)
            out.broadcast = broadcast_slot_to_string(slot)

        out.status = self.getStatus(out)

        if "genres" in a.keys():
            self.save_genres(id, a["genres"])

        # Relations
        if a.get("relations"):
            rels = []
            for edge in a.get("relations", {}).get("edges", []):
                node = edge.get("node", {})

                rel = {
                    "type": node.get("type").lower(),
                    "name": edge.get("relationType"),
                    "rel_id": int(node.get("id")),
                }
                rels.append(rel)

            if len(rels) > 0:
                self.save_relations(id, rels)

        # Characters
        if a.get("characters"):
            for edge in a.get("characters").get("edges"):
                c = edge.get("node")
                c["role"] = edge.get("role")

                # self._convertCharacter(c) #TODO

        return out

    def _convertCharacter(self, c, anime_id=None):
        # TODO - merge function

        id = self.database.getId(self.apiKey, c.get("id"), table="characters")
        out = Character()
        out.id = id
        out.name = c.get("name", {}).get("full")
        out.desc = c.get("description")

        image = c.get("image", {})
        out.picture = image.get("large") or image.get("medium")

        if anime_id is not None:
            role = c.get("role") if isinstance(c, dict) else None
            if role is None:
                role = ""
            anime_data = {anime_id: role.lower()}
            self.save_animeography(id, anime_data)

        return out

    def iterate(self, query, variables):
        page = 1
        max_pages = int(variables.get("max_pages", 10))
        while True:
            variables["page"] = page
            try:
                if hasattr(self, "session") and self.session is not None:
                    res = self.session.request(
                        "POST",
                        self.url,
                        json={"query": str(query), "variables": variables},
                    )
                else:
                    res = requests.post(
                        self.url, json={"query": str(query), "variables": variables}
                    )
            except Exception as e:
                self.log("ANILIST", "Network error during iterate():", e)
                return

            try:
                rep = res.json()
            except Exception as e:
                self.log("ANILIST", "Invalid JSON in iterate():", e)
                return

            if rep.get("errors"):
                self.log("ANILIST", f'[ERROR] - On AnilistCo: {rep.get("errors")}')
                return

            data = rep.get("data")
            if not data:
                return

            page_data = data.get("Page", {})
            if page_data is not None:
                for m in page_data.get("media", []) or []:
                    yield m

                pageInfo = page_data.get("pageInfo", {}) or {}
                if not pageInfo.get("hasNextPage"):
                    return
                page = (pageInfo.get("currentPage") or page) + 1
                if page > max_pages:
                    return

            else:
                return
