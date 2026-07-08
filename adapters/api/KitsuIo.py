import traceback
from datetime import datetime, timezone

import requests
from jsonapi_client import (Filter, Inclusion, Modifier, Session, exceptions,
                            relationships)

try:
    from .APIUtils import Anime, APIUtils, Character
except ImportError:
    # Local testing
    import os
    import sys

    sys.path.append(os.path.abspath("./"))
    from APIUtils import Anime, APIUtils, Character


def _current_anime_season() -> tuple[int, str]:
    """Return ``(year, season)`` for the current calendar anime season."""
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


def error_wrapper(func):
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except requests.exceptions.ConnectionError as e:  # Shouldn't be handled here??
            self.log(
                "ANIME_SEARCH",
                f"Error on {self.__name__}.{func.__name__}: No internet connection! -",
                e,
            )
        except requests.exceptions.ReadTimeout as e:
            self.log(
                "ANIME_SEARCH",
                f"Error on {self.__name__}.{func.__name__}: Timed out! -",
                e,
            )
        return None

    return wrapper


class KitsuIoWrapper(APIUtils):
    def __init__(self):
        APIUtils.__init__(self)
        # TODO - self.s.close() ??
        self.s = Session("https://kitsu.io/api/edge/")
        self.apiKey = "kitsu_id"
        self.mappedSites = {
            "myanimelist/anime": "mal_id",
            "anidb": "anidb_id",
            "anilist/anime": "anilist_id",
        }
        self.subtypes = ("TV", "movie")

    @error_wrapper
    def anime(self, id):
        kitsu_id = self.getId(id)
        if kitsu_id is None:
            return {}
        modifier = Inclusion(
            "genres", "mediaRelationships", "mediaRelationships.destination", "mappings"
        )
        rep = self.s.get("anime/" + str(kitsu_id), modifier).resource
        data = self._convertAnime(rep, force=True)
        return data

    @error_wrapper
    def animeCharacters(self, id):
        kitsu_id = self.getId(id)
        if kitsu_id is None:
            return []
        modifier = Inclusion("character")
        characters = self.s.iterate(
            "anime/{}/characters".format(str(kitsu_id)), modifier
        )
        for c in characters:
            yield self._convertCharacter(c, id)

    @error_wrapper
    def animePictures(self, id):
        modifier = Filter(id=id)
        rep = self.s.get("anime", modifier).resources
        if len(rep) >= 1:
            a = [rep[0].posterImage]
        else:
            a = []
        return a

    @error_wrapper
    def season(self, year, season, limit=50):
        modifier = Filter(seasonYear=year, season=season) + Inclusion(
            "genres", "mediaRelationships", "mediaRelationships.destination"
        )
        count = 0
        for a in self.s.iterate("anime", modifier):
            data = self._convertAnime(a)
            if data is None:
                continue
            yield data
            count += 1
            if count >= limit:
                return

    @error_wrapper
    def genre(self, name, limit=50):
        modifier = Filter(genres=name) + Inclusion(
            "genres", "mediaRelationships", "mediaRelationships.destination"
        )
        count = 0
        for a in self.s.iterate("anime", modifier):
            data = self._convertAnime(a)
            if data is None:
                continue
            yield data
            count += 1
            if count >= limit:
                return

    @error_wrapper
    def schedule(self, limit=50):
        seen_ids: set[int] = set()
        count = 0

        def convert_unique(raw):
            nonlocal count
            if count >= limit:
                return False
            try:
                data = self._convertAnime(raw)
            except Exception as e:
                self.log(f"An error occured: {e}")
                traceback.print_exc()
                raise
            if not data:
                return None
            data_id = (
                data.get("id") if isinstance(data, dict) else getattr(data, "id", None)
            )
            if data_id is None or int(data_id) in seen_ids:
                return None
            seen_ids.add(int(data_id))
            count += 1
            return data

        inclusion = Inclusion(
            "genres",
            "mediaRelationships",
            "mediaRelationships.destination",
            "mappings",
        )
        trending = self.s.iterate(
            "trending/anime", inclusion + Modifier("page[limit]=20")
        )
        for raw in trending:
            item = convert_unique(raw)
            if item is False:
                return
            if item:
                yield item

        modifier = inclusion + Modifier("page[limit]=20") + Modifier(
            "sort=-startDate,-endDate"
        )
        recent = self.s.iterate("anime", modifier + Filter(status="current"))
        upcoming = self.s.iterate("anime", modifier + Filter(status="upcoming"))

        try:
            r_anime = next(recent, None)
        except exceptions.DocumentError as e:
            r_anime = None
            if e.errors["status_code"] != 500:
                raise

        try:
            u_anime = next(upcoming, None)
        except exceptions.DocumentError as e:
            u_anime = None
            if e.errors["status_code"] != 500:
                raise

        while (r_anime is not None or u_anime is not None) and count < limit:
            if r_anime is not None:
                item = convert_unique(r_anime)
                if item is False:
                    return
                if item:
                    yield item
                try:
                    r_anime = next(recent, None)
                except exceptions.DocumentError as e:
                    r_anime = None
                    if e.errors["status_code"] != 500:
                        raise

            if u_anime is not None:
                item = convert_unique(u_anime)
                if item is False:
                    return
                if item:
                    yield item
                try:
                    u_anime = next(upcoming, None)
                except exceptions.DocumentError as e:
                    u_anime = None
                    if e.errors["status_code"] != 500:
                        raise

        if count >= limit:
            return

        year, season = _current_anime_season()
        season_iter = self.s.iterate(
            "anime", Filter(seasonYear=year, season=season) + inclusion
        )
        for raw in season_iter:
            item = convert_unique(raw)
            if item is False:
                return
            if item:
                yield item

    @error_wrapper
    def searchAnime(self, search, limit=50):
        modifier = (
            Filter(text=search)
            + Inclusion(
                "genres", "mediaRelationships", "mediaRelationships.destination"
            )
            # Modifier("sort=-endDate") doesn't work for some reasons
        )

        c = 1
        for a in self.s.iterate("anime", modifier):
            data = self._convertAnime(a)
            if data is None:
                continue
            yield data
            c += 1
            if c >= limit:
                break

    @error_wrapper
    def character(self, id):
        kitsu_id = self.getId(id, "characters")
        if kitsu_id is None:
            return {}
        modifier = Filter(id=kitsu_id) + Inclusion("characters", "characters.character")
        rep = self.s.get("anime", modifier).resources
        if len(rep) >= 1:
            return self._convertCharacter(rep[0])

    def _convertAnime(self, a, force=False):
        try:
            if not force and a.subtype not in self.subtypes:
                return None
        except Exception:
            # Unexpected object shape
            return None

        external_ids = {"kitsu_id": int(a.id)}
        try:
            id = self.resolve_catalog_id(external_ids)
        except Exception:
            return None

        data = Anime()
        data["id"] = id
        try:
            if a.canonicalTitle and a.canonicalTitle[-1] == ".":
                data["title"] = a.canonicalTitle[:-1]
            else:
                data["title"] = a.canonicalTitle
        except Exception:
            data["title"] = None
        try:
            if hasattr(a.posterImage, "large"):
                data["picture"] = a.posterImage.large
            else:
                data["picture"] = a.posterImage.original
        except Exception as e:
            pass

        pictures = []
        try:
            for size in ("small", "medium", "large"):
                img_url = a.posterImage.get(size)
                if img_url:
                    pictures.append({"url": img_url, "size": size})
        except Exception:
            pass

        self.save_pictures(id, pictures)

        data["title_synonyms"] = list(a.titles.values()) + [data["title"]]
        if a.startDate is None:
            data["date_from"] = None
        else:
            # Store as UTC Unix timestamp (seconds since epoch)
            # Supports dates before 1970 (negative timestamps)
            try:
                dt = datetime.fromisoformat(a.startDate)
                timestamp = int(dt.replace(tzinfo=timezone.utc).timestamp())
                # Validate timestamp is reasonable (after year 1 and before year 9999)
                if (
                    timestamp > -62135596800 and timestamp < 253402300800
                ):  # Year 1 to 9999
                    data["date_from"] = timestamp
                else:
                    data["date_from"] = None
            except Exception:
                data["date_from"] = None

        if a.endDate is None:
            data["date_to"] = None
        else:
            try:
                dt = datetime.fromisoformat(a.endDate)
                timestamp = int(dt.replace(tzinfo=timezone.utc).timestamp())
                # Validate timestamp is reasonable (after year 1 and before year 9999)
                if (
                    timestamp > -62135596800 and timestamp < 253402300800
                ):  # Year 1 to 9999
                    data["date_to"] = timestamp
                else:
                    data["date_to"] = None
            except Exception:
                data["date_to"] = None

        data["synopsis"] = a.synopsis
        data["episodes"] = int(a.episodeCount) if a.episodeCount is not None else None
        data["duration"] = int(a.episodeLength) if a.episodeLength is not None else None
        data["rating"] = a.ageRating

        data["status"] = self.getStatusFromData(data)
        # data['status'] = 'UPDATE'
        if a.youtubeVideoId is not None and a.youtubeVideoId != "":
            data["trailer"] = "https://www.youtube.com/watch?v=" + a.youtubeVideoId

        try:
            if isinstance(a.relationships.genres, relationships.MultiRelationship):
                self.save_genres(id, [g["name"] for g in a.genres])
        except Exception:
            pass

        try:
            if isinstance(
                a._relationships["mediaRelationships"], relationships.MultiRelationship
            ):
                rels = []
                for f in a.mediaRelationships:
                    rel = {
                        "type": f.destination.type,
                        "name": f.role,
                        "rel_id": f.destination.id,
                    }
                    rels.append(rel)
                self.save_relations(id, rels)
        except Exception:
            pass

        try:
            if not isinstance(a.relationships.mappings, relationships.LinkRelationship):
                for m in a.mappings:
                    api_id = m.externalId
                    site = m.externalSite
                    if site in self.mappedSites:
                        external_ids[self.mappedSites[site]] = int(api_id)
        except Exception:
            pass

        data["id"] = self.resolve_catalog_id(external_ids)
        return data

    def _convertCharacter(self, c, anime_id=None):
        try:
            mal_id = int(c.character.malId)
            kitsu_id = int(c.character.id)
        except Exception:
            return None

        # TODO - merge function

        sql = "SELECT EXISTS(SELECT 1 FROM charactersIndex WHERE (kitsu_id != ? or kitsu_id is null) and mal_id=?)"
        res = self.database.sql(
            sql,
            (
                kitsu_id,
                mal_id,
            ),
        )
        api_exist = False
        if res and len(res) > 0 and len(res[0]) > 0:
            api_exist = bool(res[0][0])
        if api_exist:
            temp_id = self.database.getId("mal_id", mal_id, table="characters")
            self.database.sql("DELETE FROM charactersIndex WHERE id=?", (temp_id,))
            self.database.sql("DELETE FROM characters WHERE id=?", (temp_id,))

        id = self.database.getId("kitsu_id", kitsu_id, table="characters")
        self.database.sql(
            "UPDATE charactersIndex SET mal_id = ? WHERE kitsu_id=?", (mal_id, kitsu_id)
        )

        try:
            self.database.save()
        except Exception:
            pass

        id = self.database.getId("kitsu_id", kitsu_id, table="characters")
        out = Character()
        out["id"] = id
        # out['role'] = c.role.lower()
        out["name"] = getattr(c.character, "name", None)

        img = getattr(c.character, "image", None)
        if img is not None:
            # image may be a dict-like or object
            try:
                out["picture"] = (
                    img.get("original")
                    if hasattr(img, "get")
                    else getattr(img, "original", None)
                )
            except Exception:
                out["picture"] = None

        out["desc"] = getattr(c.character, "description", None)

        if anime_id is not None:
            anime_data = {anime_id: c.role.lower()}
            self.save_animeography(id, anime_data)

        return out
