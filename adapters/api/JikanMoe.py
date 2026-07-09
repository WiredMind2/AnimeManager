import re
import time
from datetime import datetime, timezone

import requests

try:
    from .APIUtils import Anime, APIUtils, Character, EnhancedSession
except ImportError:
    from APIUtils import Anime, APIUtils, Character, EnhancedSession


def _current_anime_season() -> tuple[int, str]:
    """Return ``(year, season)`` for the current broadcast quarter."""
    now = datetime.now(timezone.utc)
    month = now.month
    if month <= 3:
        season = "winter"
    elif month <= 6:
        season = "spring"
    elif month <= 9:
        season = "summer"
    else:
        season = "fall"
    return now.year, season


class JikanMoeWrapper(APIUtils):
    def __init__(self):
        super().__init__()
        self.session = EnhancedSession(timeout=30)
        self.base_url = "https://api.jikan.moe/v4"
        self.cooldown = 2
        self.last = time.time() - self.cooldown
        self.apiKey = "mal_id"

        self.mapped_external = {
            "AnimeDB": {"api_key": "anidb_id", "regex": r".+aid=(\d+).*"}
        }

    def anime(self, id):
        mal_id = self.getId(id)
        if mal_id is None:
            return {}
        self.delay()
        a = self.get("/anime/{id}/full", id=mal_id)
        if not a or not isinstance(a, dict):
            return {}
        data_obj = a.get("data")
        if not data_obj:
            return {}
        return self._convertAnime(data_obj)

    def animeCharacters(self, id):
        mal_id = self.getId(id)
        if mal_id is None:
            return []
        self.delay()
        rep = self.get("/anime/{id}/characters", id=mal_id)
        if not rep or not isinstance(rep, dict):
            return []
        for data in rep.get("data", []):
            char = data.get("character")
            role = data.get("role")
            yield self._convertCharacter(char, role, id)

    def animePictures(self, id):
        self.delay()
        a = self.get("/anime/{id}/pictures", id=id)
        if not a or not isinstance(a, dict):
            return []
        return a.get("pictures", [])

    def schedule(self, limit=50):
        self.delay()
        seen_mal_ids: set[int] = set()
        count = 0

        def convert_unique(raw):
            nonlocal count
            if count >= limit:
                return False
            mal_id = raw.get("mal_id") if isinstance(raw, dict) else None
            if mal_id is None:
                return None
            mal_id = int(mal_id)
            if mal_id in seen_mal_ids:
                return None
            anime = self._convertAnime(raw)
            if not anime:
                return None
            seen_mal_ids.add(mal_id)
            count += 1
            return anime

        rep = self.get("/schedules")
        if rep.get("status", None) == 429:
            return

        self.getDatabase()

        if rep.get("data", None):
            for anime in rep["data"]:
                item = convert_unique(anime)
                if item is False:
                    return
                if item:
                    yield item

        if count >= limit:
            return

        year, season = _current_anime_season()
        for anime in self.season(year, season, limit=limit - count):
            mal_id = getattr(anime, "id", None)
            ext = getattr(anime, "_schedule_external_ids", None) or {}
            if mal_id is None:
                mal_id = ext.get("mal_id")
            if mal_id is None:
                yield anime
                count += 1
                if count >= limit:
                    return
                continue
            mal_id = int(mal_id)
            if mal_id in seen_mal_ids:
                continue
            seen_mal_ids.add(mal_id)
            count += 1
            yield anime
            if count >= limit:
                return

    def season(self, year, season, limit=50):
        self.delay()
        season_key = str(season or "").strip().lower()
        if season_key not in ("winter", "spring", "summer", "fall"):
            return
        rep = self.get(f"/seasons/{int(year)}/{season_key}")
        if not rep or not isinstance(rep, dict):
            return
        if rep.get("status") == 429:
            return
        count = 0
        for anime in rep.get("data", []):
            data = self._convertAnime(anime)
            if not data:
                continue
            yield data
            count += 1
            if count >= limit:
                return

    def searchAnime(self, search, limit=50):
        self.delay()
        rep = self.get("/anime", q=search, order_by="end_date", sort="desc")
        if not rep or not isinstance(rep, dict):
            return
        count = 0
        for a in rep.get("data", []):
            data = self._convertAnime(a)
            if len(data) != 0:
                yield data
                count += 1
                if count >= limit:
                    return

        try:
            for a in self.searchAnimeLetter(search[0], limit=limit - count):
                yield a
        except GeneratorExit:
            pass

    def searchAnimeLetter(self, letter, limit=50):
        page = 1
        count = 0
        looping = True
        while looping:
            self.delay()
            rep = self.get(
                "/anime",
                letter=letter,
                order_by="end_date",
                sort="desc",
                page=page,
            )
            data = rep.get("data")
            if data:
                for a in data:
                    data = self._convertAnime(a)
                    if len(data) != 0:
                        yield data
                        count += 1
                        if count >= limit:
                            return
            if "pagination" in rep and rep["pagination"]["has_next_page"]:
                page += 1
            else:
                looping = False

    def character(self, id):
        mal_id = self.getId(id, table="characters")
        self.delay()
        c = self.get("/characters/{id}", id=mal_id)
        if not c or not isinstance(c, dict):
            return {}
        return self._convertCharacter(c.get("data"))

    def _convertAnime(self, a):
        external_ids = {"mal_id": int(a["mal_id"])}
        if getattr(self, "schedule_light", False):
            out = Anime()
            out._schedule_external_ids = external_ids
            out["title"] = a["title"]
            if a["title"][-1] == ".":
                out["title"] = a["title"][:-1]

            keys = ["title", "title_english", "title_japanese"]
            titles = []
            for key in keys:
                if key in a.keys() and a[key] is not None:
                    titles.append(a[key])
            if "title_synonyms" in a.keys():
                titles += a["title_synonyms"]
            out["title_synonyms"] = titles

            if "aired" in a.keys():
                for i in ("from", "to"):
                    v = a["aired"]["prop"].get(i, None)
                    if v and not None in v.values():
                        out["date_" + i] = int(
                            datetime(**v, tzinfo=timezone.utc).timestamp()
                        )
                    else:
                        out["date_" + i] = None
            else:
                out["date_from"] = None
                out["date_to"] = None

            out["picture"] = (
                a["images"]["jpg"].get("large_image_url", None)
                or a["images"]["jpg"]["image_url"]
            )
            out["synopsis"] = a["synopsis"] if "synopsis" in a.keys() else None
            out["episodes"] = a["episodes"] if "episodes" in a.keys() else None
            duration = (
                a["duration"].split(" ")[0] if "duration" in a.keys() else None
            )
            out["duration"] = (
                int(duration) if duration and duration != "Unknown" else None
            )
            out["rating"] = (
                a["rating"].split("-")[0].rstrip()
                if "rating" in a.keys() and a["rating"]
                else None
            )
            if "broadcast" in a.keys() and a["broadcast"]["day"] is not None:
                weekdays = (
                    "Mondays",
                    "Tuesdays",
                    "Wednesdays",
                    "Thursdays",
                    "Fridays",
                    "Saturdays",
                    "Sundays",
                )
                w = weekdays.index(a["broadcast"]["day"])
                h, m = a["broadcast"]["time"].split(":")[:2]
                out["broadcast"] = "{}-{}-{}".format(w, h, m)
            out["trailer"] = a["trailer_url"] if "trailer_url" in a.keys() else None
            if out["date_from"] is None:
                out["status"] = "UPDATE"
            else:
                out["status"] = (
                    self.getStatus(out) if "status" in a.keys() else None
                )
            return out

        id = self.resolve_catalog_id(external_ids)
        out = Anime()

        out["id"] = id
        out["title"] = a["title"]
        if a["title"][-1] == ".":
            out["title"] = a["title"][:-1]

        keys = ["title", "title_english", "title_japanese"]
        titles = []
        for key in keys:
            if key in a.keys() and a[key] is not None:
                titles.append(a[key])
        if "title_synonyms" in a.keys():
            titles += a["title_synonyms"]

        out["title_synonyms"] = titles

        if "aired" in a.keys():
            for i in ("from", "to"):
                v = a["aired"]["prop"].get(i, None)
                if v and not None in v.values():
                    # Schema stores ``date_from`` / ``date_to`` as Unix
                    # timestamps (see ``Getters.getStatus`` which calls
                    # ``datetime.fromtimestamp``). The previous code
                    # used ``datetime(**v).toordinal()`` which returns
                    # *days since year 1* (e.g. ~7.4e5 for 2026 dates)
                    # -- those small values silently passed the
                    # persistence layer (which was itself broken on
                    # MariaDB pools, masking the issue) but produced
                    # nonsensical airing windows and pushed Jikan rows
                    # to the bottom of any ``ORDER BY date_from DESC``
                    # query that mixed providers. Use a UTC timestamp
                    # so all providers agree on the unit.
                    out["date_" + i] = int(
                        datetime(**v, tzinfo=timezone.utc).timestamp()
                    )
                else:
                    out["date_" + i] = None
        else:
            out["date_from"] = None
            out["date_to"] = None

        out["picture"] = (
            a["images"]["jpg"].get("large_image_url", None)
            or a["images"]["jpg"]["image_url"]
        )

        pictures = []

        sizes = {
            "image_url": "medium",
            "small_image_url": "small",
            "large_image_url": "large",
        }
        pictures = []
        # for type, imgs in a['images'].items():
        for size, url in a["images"]["jpg"].items():  # Ignoring webp images
            size_lbl = sizes[size]
            img = {"url": url, "size": size_lbl}
            pictures.append(img)

        self.save_pictures(id, pictures)

        out["synopsis"] = a["synopsis"] if "synopsis" in a.keys() else None
        out["episodes"] = a["episodes"] if "episodes" in a.keys() else None
        duration = a["duration"].split(" ")[0] if "duration" in a.keys() else None
        out["duration"] = int(duration) if duration and duration != "Unknown" else None
        out["status"] = None  # a['status'] if 'status' in a.keys() else None
        out["rating"] = (
            a["rating"].split("-")[0].rstrip()
            if "rating" in a.keys() and a["rating"]
            else None
        )
        if "broadcast" in a.keys() and a["broadcast"]["day"] is not None:
            weekdays = (
                "Mondays",
                "Tuesdays",
                "Wednesdays",
                "Thursdays",
                "Fridays",
                "Saturdays",
                "Sundays",
            )

            if a["broadcast"]["day"] not in weekdays:
                raise ValueError(f"{a['broadcast']['day']} is not in weekdays!")

            w = weekdays.index(a["broadcast"]["day"])
            h, m = a["broadcast"]["time"].split(":")[:2]

            self.save_broadcast(id, w, h, m)

            # TODO - Should be removed
            out["broadcast"] = "{}-{}-{}".format(w, h, m)

        # out['broadcast'] = a['broadcast']['day'] + '-' +  if 'broadcast' in a.keys() else None
        out["trailer"] = a["trailer_url"] if "trailer_url" in a.keys() else None

        if out["date_from"] is None:
            out["status"] = "UPDATE"
            return {}
        else:
            out["status"] = self.getStatus(out) if "status" in a.keys() else None

        if "relations" in a.keys():
            rels = []
            for relation in a["relations"]:
                rel_type = relation["relation"]
                entries = relation["entry"]
                for entry in entries:
                    rel = {
                        "type": entry["type"],
                        "name": relation["relation"],
                        "rel_id": int(entry["mal_id"]),
                    }
                    rels.append(rel)
            if len(rels) > 0:
                self.save_relations(id, rels)

        if "external" in a.keys():
            for external in a["external"]:
                if external["name"] in self.mapped_external:
                    ext_data = self.mapped_external[external["name"]]
                    match = re.match(ext_data["regex"], external["url"])
                    if match:
                        api_key = ext_data["api_key"]
                        external_ids[api_key] = int(match.group(1))

        out["id"] = self.resolve_catalog_id(external_ids)
        return out

    def _convertCharacter(self, c, role: str | None = None, anime_id=None):
        c_id = self.database.getId("mal_id", int(c["mal_id"]), table="characters")

        out = Character()
        out.id = c_id

        out.name = c["name"]
        if role is not None:
            out.role = str(role).strip().lower()
        # TODO - Use multiple images?
        out.picture = c["images"]["jpg"]["image_url"]

        out.desc = c.get("about")

        # TODO - c.get('nicknames') / c.get('kanji')?

        if anime_id is not None and role is not None:
            animes_data = {anime_id: role.lower()}
            self.save_animeography(c_id, animes_data)

        return out

    def get(self, endpoint, **kwargs):
        path_kwargs = {}
        query_kwargs = {}
        for key, value in kwargs.items():
            if "{" + key + "}" in endpoint:
                path_kwargs[key] = value
            else:
                query_kwargs[key] = value
        if path_kwargs:
            endpoint = endpoint.format(**path_kwargs)
        url = self.base_url + endpoint
        try:
            # Use provided session if available
            if hasattr(self, "session") and self.session is not None:
                r = self.session.request("GET", url, params=query_kwargs or None)
            else:
                r = requests.get(url, params=query_kwargs or None)
        except Exception as e:
            self.log("API_WRAPPER", "[Jikan.moe] - Error: ", e)
            return {}
        else:
            try:
                return r.json()
            except Exception:
                self.log("API_WRAPPER", "[Jikan.moe] - Invalid JSON response")
                return {}

    def delay(self):
        if time.time() - self.last < self.cooldown:
            time.sleep(max(self.cooldown - (time.time() - self.last), 0))
        self.last = time.time()
