import os
import sys
from enum import Enum
from functools import wraps
from typing import List, Optional, Tuple, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.append(os.path.abspath("../"))
from AnimeManager import Manager, search_engines  # type: ignore


class Anime(BaseModel):
    id: int
    title: str
    picture: Optional[str]
    title_synonyms: list
    date_from: Optional[int]
    date_to: Optional[int]
    synopsis: Optional[str]
    episodes: Optional[int]
    duration: Optional[int]
    rating: Optional[str]
    status: Optional[str]
    trailer: Optional[str]
    genres: list = []


class Torrent(BaseModel):
    link: str
    name: str
    size: int
    seeds: int
    leech: int


class FilterEnum(str, Enum):
    LIKED = "LIKED"
    SEEN = "SEEN"
    WATCHING = "WATCHING"
    WATCHLIST = "WATCHLIST"
    FINISHED = "FINISHED"
    AIRING = "AIRING"
    UPCOMING = "UPCOMING"
    RATED = "RATED"
    SEASON = "SEASON"
    RANDOM = "RANDOM"
    NONE = "NONE"
    DEFAULT = "DEFAULT"


def get_user(user_id: int):
    # TODO
    return {"name": "user"}


def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user_id = kwargs.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated!")
        return func(*args, **kwargs)

    return wrapper


manager = Manager(remote=True)
app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get(
    "/anime/{anime_id}",
    response_model=Anime,
    tags=["Anime"],
    responses={404: {"description": "Anime not found"}},
)
def get_anime(anime_id: int, reload: bool = False):
    """Get anime by id"""

    # TODO - Force reload?

    try:
        data = manager.api.anime(anime_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"An unhandled error occurred: {str(e)}"
        )

    if not data:
        raise HTTPException(
            status_code=404, detail=f"Anime with id {anime_id} not found!"
        )

    return data


@app.get(
    "/animelist",
    response_model=List[Anime],
    tags=["Anime"],
    responses={400: {"description": "Bad request"}},
)
def get_anime_list(
    filter: FilterEnum = FilterEnum.NONE,
    user_id: int = None,
    list_start: int = 0,
    list_stop: int = 50,
):
    """Get anime list using a filter. If user_id is provided, the list can be filtered by the user's tags."""
    user_tags = [
        FilterEnum.LIKED,
        FilterEnum.SEEN,
        FilterEnum.WATCHING,
        FilterEnum.WATCHLIST,
    ]

    if user_id is None and filter in user_tags:
        raise HTTPException(
            status_code=400, detail="User ID is required for this filter!"
        )

    listrange = (list_start, list_stop)
    try:
        alist, nextlist = manager._database_manager.get_anime_list(filter.value, listrange, None, user_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"An unhandled error occurred: {str(e)}"
        )

    out = []
    for anime in alist:
        anime.title_synonyms
        anime.genres
        out.append(dict(anime))

    return out


@app.get(
    "/search",
    response_model=List[Anime],
    tags=["Anime"],
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated!"},
    },
)
@require_auth
def search(query: str, user_id: int, limit: int = 50):
    """Search for anime by title. You must provide an user_id, in order to avoid spam attacks."""

    data = manager.api.searchAnime(query, limit)

    out = []
    for (
        anime
    ) in data:  # TODO - Figure out how to either speed up search OR stream results
        print(anime.title)
        out.append(anime)

    return out


@app.get(
    "/torrents",
    response_model=List[Torrent],
    tags=["Torrents"],
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated!"},
    },
)
@require_auth
def search_torrents(id: int, user_id: int):
    """Search for torrents for an anime. You must provide an user_id, in order to avoid spam attacks."""

    data = manager.getDatabase().get(id=id, table="anime")
    titles = data.title_synonyms

    titles = list(set(titles) | {data.title})

    fetcher = search_engines.search(titles)

    out = []
    for torrent in fetcher:  # TODO - Same as search
        out.append(torrent)

    return out


@app.get(
    "/download/{anime_id}",
    tags=["Torrents"],
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated!"},
    },
)
@require_auth
def start_download(anime_id: int, link: str, user_id: int):
    """Start downloading a torrent from a magnet link."""
    pass


@app.get(
    "/torrents/progress/{anime_id}",
    tags=["Torrents"],
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated!"},
    },
)
@require_auth
def torrent_progress(anime_id: int, user_id: int):
    """Get torrent download progress."""
    pass

    # progress = self.get_torrents_progress(id)
    # torrents = [{'hash': k} | v for k, v in progress.items()]


@app.get(
    "/episodes/{anime_id}",
    tags=["Episodes"],
    responses={
        400: {"description": "Bad request"},
    },
)
def get_episodes(anime_id: int):
    """Get currently available episodes for an anime."""
    pass
    # source = self.main.getFolder(anime=anime)
    # episodes = self.main.getEpisodes(source)


@app.get(
    "/watch/{anime_id}/{file}",
    tags=["Episodes"],
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated!"},
    },
)
@require_auth
async def watch(anime_id: int, file: str, user_id: int):
    """Watch an anime episode."""

    # This should return an url generated by ffmpeg
    pass


@app.post(
    "/like/{anime_id}",
    tags=["Actions"],
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated!"},
    },
)
@require_auth
def like_anime(anime_id: int, user_id: int):
    """Like an anime."""
    pass


@app.post(
    "/tag/{anime_id}",
    tags=["Actions"],
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated!"},
    },
)
@require_auth
def tag_anime(anime_id: int, tag: str, user_id: int):
    """Tag an anime."""
    pass


@app.post(
    "/seen/{anime_id}/{file}",
    tags=["Actions"],
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated!"},
    },
)
@require_auth
def seen_anime(anime_id: int, file: str, user_id: int):
    """Mark an anime as seen."""
    pass
