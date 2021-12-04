from APIUtils import APIUtils, Anime, Character, log
from jsonapi_client import Session, Filter, Modifier, Inclusion, relationships
import json


class KitsuIoWrapper(APIUtils):
    def __init__(self, dbPath):
        super().__init__(dbPath)
        self.s = Session('https://kitsu.io/api/edge/')
        self.apiKey = "kitsu_id"
        self.mappedSites = {"myanimelist/anime": "mal_id",
                            "anidb": "anidb_id", "anilist/anime": "anilist_id"}
        self.subtypes = ('TV', 'movie')

    def anime(self, id, save=True):
        kitsu_id = self.getId(id)
        if kitsu_id is None:
            return {}
        modifier = Inclusion("genres", "mediaRelationships",
                             "mediaRelationships.destination", "mappings")
        rep = self.s.get('anime/' + str(kitsu_id), modifier).resource
        data = self._convertAnime(rep, force=True)
        if save:
            self.database.set(data, table="anime")
        return data

    def animeCharacters(self, id):
        kitsu_id = self.getId(id)
        if kitsu_id is None:
            return []
        modifier = Inclusion("character")
        characters = self.s.iterate(
            'anime/{}/characters'.format(str(kitsu_id)), modifier)
        for c in characters:
            yield self._convertCharacter(c, id)

    def animePictures(self, id):
        modifier = Filter(id=id)
        rep = self.s.get('anime', modifier).resources
        if len(rep) >= 1:
            a = [rep[0].posterImage]
        else:
            a = []
        return a

    def season(self, year, season, save=True):
        modifier = Filter(seasonYear=year,
                          season=season) + Inclusion("genres",
                                                     "mediaRelationships",
                                                     "mediaRelationships.destination")
        for a in self.s.iterate('anime', modifier):
            data = self._convertAnime(a)
            if data is None:
                continue
            if save:
                self.database.set(data, table="anime")
            yield data

    def schedule(self, limit=100):
        def getSchedule():
            modifier = Inclusion("genres", "mediaRelationships",
                                 "mediaRelationships.destination", "mappings")
            trending = self.s.iterate('trending/anime', modifier)
            for a in trending:
                yield a
            modifier += Modifier("sort=-startDate,-endDate")
            r_modifier = modifier + Filter(status="current")
            recent = self.s.iterate('anime', r_modifier)
            u_modifier = modifier + Filter(status="upcoming")
            upcoming = self.s.iterate('anime', u_modifier)
            r_anime, u_anime = next(recent, None), next(upcoming, None)
            while r_anime is not None or u_anime is not None:
                if r_anime is not None:
                    yield r_anime
                if u_anime is not None:
                    yield u_anime
                r_anime, u_anime = next(recent, None), next(upcoming, None)

        out = []
        schedule = getSchedule()

        for c, a in enumerate(schedule):
            data = self._convertAnime(a)
            if data is None:
                continue

            yield data
            if c >= limit:
                break

    def searchAnime(self, search, save=True, limit=50):
        modifier = Filter(text=search) + Inclusion("genres",
                                                   "mediaRelationships", "mediaRelationships.destination")
        c = 1
        for a in self.s.iterate('anime', modifier):
            data = self._convertAnime(a)
            if data is None:
                continue
            if save:
                self.database.set(data, table="anime")
            yield data
            c += 1
            if c >= limit:
                break

    def character(self, id):
        kitsu_id = self.getId(id, "characters")
        if kitsu_id is None:
            return {}
        modifier = Filter(id=kitsu_id) + \
            Inclusion("characters", "characters.character")
        rep = self.s.get('anime', modifier).resources
        if len(rep) >= 1:
            return self._convertCharacter(rep[0])

    def _convertAnime(self, a, force=False):
        self.database = self.getDatabase()
        self._mapAnimes(a)
        if not force and a.subtype not in self.subtypes:
            return None
        id = self.database.getId("kitsu_id", int(a.id))

        data = Anime()
        # data['kitsu_id'] = int(a.id)
        data['id'] = id
        if a.canonicalTitle[-1] == ".":
            data['title'] = a.canonicalTitle[:-1]
        else:
            data['title'] = a.canonicalTitle
        try:
            data['picture'] = a.posterImage.small
        except BaseException:
            pass

        if len(a.titles) >= 1:
            data['title_synonyms'] = json.dumps(list(a.titles.values()))
        else:
            data['title_synonyms'] = None
        data['date_from'] = a.startDate
        data['date_to'] = a.endDate
        data['synopsis'] = a.synopsis
        data['episodes'] = int(
            a.episodeCount) if a.episodeCount is not None else None
        data['duration'] = int(
            a.episodeLength) if a.episodeLength is not None else None
        data['rating'] = a.ageRating
        status = {
            'current': 'AIRING',
            'finished': 'FINISHED',
            'tba': 'UPCOMING',
            'unreleased': 'UNKNOWN',
            'upcoming': 'UPCOMING'}
        data['status'] = self.getStatus(data)
        # data['status'] = 'UPDATE'
        if a.youtubeVideoId is not None and a.youtubeVideoId != "":
            data['trailer'] = "https://www.youtube.com/watch?v=" + a.youtubeVideoId

        genres = []
        if isinstance(a.relationships.genres, relationships.MultiRelationship):
            for g in a.genres:
                if not self.database.exist(g.id, "genres", "kitsu_id"):
                    self.database.sql(
                        "INSERT INTO genres(kitsu_id,name) VALUES(?,?)", (g.id, g.name), save=False)
                genres.append(
                    self.database.sql(
                        "SELECT id FROM genres WHERE kitsu_id=?",
                        (g.id,
                         ),
                        save=False)[0][0])
        data['genres'] = json.dumps(genres)

        if isinstance(
                a._relationships['mediaRelationships'],
                relationships.MultiRelationship):
            for f in a.mediaRelationships:
                if f.destination.type == "anime":  # TODO
                    rel_id = self.database.getId("kitsu_id", f.destination.id)
                    exist = bool(
                        self.database.sql(
                            "SELECT EXISTS(SELECT 1 FROM related WHERE id=? AND relation=?);",
                            (id,
                             f.role))[0][0])
                    if exist:
                        rel_ids = json.loads(
                            self.database.sql(
                                "SELECT rel_id FROM related WHERE id=? AND relation=?;", (id, f.role))[0][0])
                        if rel_id not in rel_ids:
                            rel_ids.append(rel_id)
                        rel_ids = json.dumps(rel_ids)
                        self.database.sql(
                            "UPDATE related SET rel_id=? WHERE id=? AND relation=?;", (rel_ids, id, f.role))
                    else:
                        rel_ids = json.dumps([rel_id])
                        self.database.sql(
                            "INSERT INTO related(id,relation,rel_id) VALUES(?,?,?)", (id, f.role, rel_ids))
                    if not self.database.exist(id=rel_id, table="anime"):
                        self.database.set(
                            {'id': rel_id, 'title': a.canonicalTitle, 'status': 'UPDATE'}, table="anime", save=False)
        try:
            self.database.save()
        except BaseException:
            log("KITSU.IO API", "Error while saving anime")
        return data

    def _convertCharacter(self, c, anime_id=None):
        mal_id = int(c.character.malId)
        kitsu_id = int(c.character.id)

        sql = "SELECT EXISTS(SELECT 1 FROM charactersIndex WHERE (kitsu_id != ? or kitsu_id is null) and mal_id=?)"
        api_exist = bool(self.database.sql(sql, (kitsu_id, mal_id,))[0][0])
        id = self.database.getId("kitsu_id", kitsu_id, table="characters")
        if api_exist:
            temp_id = self.database.getId("mal_id", mal_id, table="characters")
            self.database.remove("id", id=temp_id, table=table)
        self.database.sql(
            "UPDATE charactersIndex SET mal_id = ? WHERE kitsu_id=?",
            (mal_id,
             kitsu_id))

        try:
            self.database.save()
        except BaseException:
            pass

        id = self.database.getId("kitsu_id", kitsu_id, table="characters")
        out = Character()
        out['id'] = id
        if anime_id is not None:
            out['anime_id'] = anime_id
        out['role'] = c.role.lower()
        out['name'] = c.character.name
        if c.character.image is not None:
            out['picture'] = c.character.image['original']
        out['desc'] = c.character.description

        return out

    def _mapAnimes(self, a):
        if isinstance(a.relationships.mappings,
                      relationships.LinkRelationship):
            return False
        kitsu_id = int(a.id)
        sql = "SELECT EXISTS(SELECT 1 FROM indexList WHERE (kitsu_id != ? or kitsu_id is null) and {}=?)"
        for m in a.mappings:
            api_id = m.externalId
            site = m.externalSite
            if site in self.mappedSites.keys():
                api_key = self.mappedSites[site]
                api_exist = bool(self.database.sql(sql.format(api_key), (kitsu_id, api_id,))[0][0])
                id = self.database.getId("kitsu_id", kitsu_id)
                if api_exist:
                    temp_id = self.database.getId(api_key, api_id)
                    self.database.remove(None, id=temp_id)
                    # Tag / like
                    tag_kitsu_exist, tag_api_exist = self.database.exist(id=id, table="tag"), self.database.exist(id=temp_id, table="tag")
                    if tag_api_exist and not tag_kitsu_exist:
                        tag = self.database(id=temp_id, table="tag")
                        tag['id'] = id
                        self.database.set(tag, table="tag")
                        self.database.remove("id", id=temp_id, table="tag")

                    like_kitsu_exist, like_api_exist = self.database.exist(id=id, table="like"), self.database.exist(id=temp_id, table="like")
                    if like_api_exist and not like_kitsu_exist:
                        like = self.database(id=temp_id, table="like")
                        like['id'] = id
                        self.database.set(like, table="like")
                        self.database.remove("id", id=temp_id, table="like")
                self.database.sql("UPDATE indexList SET {} = ? WHERE kitsu_id=?".format(
                    api_key), (api_id, kitsu_id))

        try:
            self.database.save()
        except BaseException:
            pass
        return True
