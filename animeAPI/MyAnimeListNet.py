import json
import os
import secrets
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import BaseServer

import requests

try:
    from .APIUtils import Anime, APIUtils, Character
except ImportError:
    from APIUtils import Anime, APIUtils, Character


class MyAnimeListNetWrapper(APIUtils):
    def __init__(self, tokenPath="token.json"):
        # Initialize parent utilities (logging, database getters)
        super().__init__()
        # MAL OAuth client credentials (may be overridden by settings)
        self.CLIENT_ID = "12811732694cf9a5ce1eff0694af5dc8"
        self.CLIENT_SECRET = (
            "fbf4c615abc334263ac2a3c92386586bafa067619be7a4f3fb7c2f6824f2bf03"
        )
        self.hostName = "127.0.0.1"
        self.serverPort = 2412
        # Token file stored in the animeAPI package by default
        self.tokenPath = os.path.join(os.path.dirname(__file__), tokenPath)
        # Do not trigger interactive auth flow during construction. getToken will
        # only read/refresh existing token file. To obtain a new token interactively
        # call getNewToken() explicitly.
        self.token = None
        try:
            self.token = self.getToken()
        except Exception:
            # Ensure constructor does not raise on lack of network or missing files
            self.log("MAL", "getToken failed during init; continuing without token")

        self.baseUrl = "https://api.myanimelist.net/v2/"

        self.apiKey = "mal_id"

        fields = (
            "alternative_titles",
            "average_episode_duration",
            "broadcast",
            "end_date",
            "genres",
            "id",
            "main_picture",
            "num_episodes",
            "start_date",
            "status",
            "synopsis",
            "title",
            "related_anime",
            "rating",
        )
        self.fields = ",".join(fields)

    def anime(self, id, relations=False):
        mal_id = self.getId(id)
        if mal_id is None:
            return {}

        a = self.get("anime", mal_id, fields=self.fields)
        if not a:
            return {}
        data = self._convertAnime(a)
        return data

    def searchAnime(self, search, save=True, limit=50):
        rep = self.get("anime", q=search, limit=limit, fields=self.fields)

        count = 0
        looping = True
        while looping:
            if "data" not in rep:
                looping = False
                break

            for a in rep["data"]:
                data = self._convertAnime(a["node"])

                if len(data) != 0:
                    yield data

                    count += 1
                    if count >= limit:
                        return

            if rep.get("paging", {}).get("next", None):
                next_url = rep["paging"]["next"]
                rep = self.get(next_url)
            else:
                looping = False

    def _convertAnime(self, a, relations=False):
        id = self.database.getId("mal_id", int(a["id"]))
        out = Anime()

        out["id"] = id
        # out["mal_id"] = a["mal_id"]
        out["title"] = a["title"]
        if a["title"][-1] == ".":
            out["title"] = a["title"][:-1]

        titles = [a["title"]]
        if "alternative_titles" in a.keys():
            for sub in a["alternative_titles"].values():
                if isinstance(sub, list):
                    titles += sub
                else:
                    titles.append(sub)

        out["title_synonyms"] = titles

        epoch = datetime(1970, 1, 1)
        if "start_date" in a.keys() and len(a["start_date"].split("-")) == 3:
            d = datetime.fromisoformat(a["start_date"])
            out["date_from"] = int((d - epoch).total_seconds())
        else:
            out["date_from"] = None

        if "end_date" in a.keys() and len(a["end_date"].split("-")) == 3:
            d = datetime.fromisoformat(a["end_date"])
            out["date_to"] = int((d - epoch).total_seconds())
        else:
            out["date_to"] = None

        out["picture"] = (
            list(a["main_picture"].items())[-1][1]
            if "main_picture" in a.keys()
            else None
        )

        pictures = []
        if "main_picture" in a.keys():
            for size, url in a["main_picture"].items():
                if size in ("small", "medium", "large"):
                    pictures.append({"url": url, "size": size})

        self.save_pictures(id, pictures)

        out["synopsis"] = a["synopsis"] if "synopsis" in a.keys() else None
        out["episodes"] = a["num_episodes"] if "num_episodes" in a.keys() else None
        out["duration"] = (
            a["average_episode_duration"] // 60
            if "average_episode_duration" in a.keys()
            else None
        )
        out["status"] = None  # a['status'] if 'status' in a.keys() else None
        out["rating"] = a["rating"].upper() if "rating" in a.keys() else None
        if "broadcast" in a.keys() and "start_time" in a["broadcast"].keys():
            weekdays = (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
            weekday = a["broadcast"]["day_of_the_week"]

            if weekday in weekdays:  # Can be 'other' -> Not scheduled once per week
                w = weekdays.index(weekday)
                h, m = a["broadcast"]["start_time"].split(":")[:2]

                self.save_broadcast(id, w, h, m)

                out["broadcast"] = "{}-{}-{}".format(
                    w, h, m
                )  # TODO - Should be removed

        # out['trailer'] = a['trailer_url'] if 'trailer_url' in a.keys() else None

        if out["date_from"] is None:
            out["status"] = "UPDATE"
        else:
            out["status"] = self.getStatus(out) if "status" in a.keys() else None

        if "genres" in a.keys():
            self.save_genres(id, [g["name"] for g in a["genres"]])

        if "related_anime" in a.keys():
            rels = []
            for relation in a["related_anime"]:
                node = relation["node"]
                if "main_picture" not in node:
                    continue
                rel = {
                    "type": "anime",
                    "name": relation["relation_type_formatted"],
                    "rel_id": node["id"],
                }
                rels.append(rel)
            self.save_relations(id, rels)

        return out

    def _convertCharacter(self, c, anime_id=None):
        # MyAnimeList character responses vary depending on endpoint. Common shapes:
        # - When coming from /characters/{id}: keys like 'id','name','about','images'
        # - When nested under anime character lists: may be under 'character' key
        # Accept either dict representing character or an envelope with 'character'.
        if c is None:
            return {}

        # Unwrap envelope if needed
        if isinstance(c, dict) and "character" in c:
            char = c["character"]
        else:
            char = c

        # Determine external MAL id if present (be defensive about types)
        mal_id = None
        if isinstance(char, dict):
            if "id" in char:
                try:
                    mal_id = int(char["id"])
                except Exception:
                    mal_id = None
            elif "mal_id" in char:
                try:
                    mal_id = int(char["mal_id"])
                except Exception:
                    mal_id = None

        # If we have an external mal_id, map it to internal id in characters table
        if mal_id is not None:
            try:
                internal_id = self.database.getId("mal_id", mal_id, table="characters")
            except Exception:
                # If mapping fails, leave id None
                internal_id = None
        else:
            internal_id = None

        out = Character()
        if internal_id is not None:
            out["id"] = internal_id

        # Name
        name = None
        if isinstance(char, dict):
            name = char.get("name") or char.get("full") or char.get("given_name")
        if name is None:
            name = ""
        out["name"] = name

        # Picture: MAL uses 'images' -> {'jpg':{'image_url':...}, 'webp':...}
        pic = None
        if isinstance(char, dict):
            imgs = char.get("images") or char.get("image") or {}
            if isinstance(imgs, dict):
                # prefer jpg.original or jpg.image_url
                jpg = imgs.get("jpg") if isinstance(imgs.get("jpg"), dict) else None
                if jpg:
                    pic = jpg.get("image_url") or jpg.get("large") or jpg.get("small")
                else:
                    # some endpoints return a single url string
                    if isinstance(imgs, str):
                        pic = imgs
        if pic:
            out["picture"] = pic

        # Description
        desc = None
        if isinstance(char, dict):
            desc = char.get("about") or char.get("description") or char.get("desc")
        out["desc"] = desc

        # Role/animeography
        if anime_id is not None:
            # role might be provided in the envelope (c.get('role') or top-level 'role')
            role = None
            if isinstance(c, dict):
                role = c.get("role") or c.get("character_role")
            if role is None:
                # default unknown
                role = "unknown"
            animes = {anime_id: role.lower()}
            if internal_id is not None:
                self.save_animeography(internal_id, animes)
            out["animeography"] = animes

        return out

    # --------------------------------------------

    def get(self, *args, **kwargs):
        # If no token is available, behave gracefully and return empty dict
        if self.token is None:
            return {}

        # Support calling get with a full URL as the first (and only) arg
        if len(args) == 1 and isinstance(args[0], str) and args[0].startswith("http"):
            url = args[0]
        else:
            url = self.baseUrl + "/".join(map(str, args))

        if len(kwargs) > 0:
            sep = "&"
            query = sep.join(str(k) + "=" + str(v) for k, v in kwargs.items())
            if "?" in url:
                url += "&" + query
            else:
                url += "?" + query

        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            r = requests.get(url, headers=headers)
        except requests.exceptions.ConnectionError:
            return {}
        else:
            # Return parsed json when possible, otherwise raw text
            try:
                return r.json()
            except ValueError:
                return r.text

    def check_validity(self, access_token, refresh_token=None):
        url = "https://api.myanimelist.net/v2/users/@me"
        try:
            rep = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
        except requests.exceptions.ConnectionError:
            return False

        if rep.status_code == 401:
            rep.close()
            return False
        user = rep.json()
        rep.close()

        # self.log(f">>> Greetings {user['name']}! <<<")
        return True

    def getNewToken(self, threaded=False):
        if threaded is False:
            threading.Thread(target=self.getNewToken, args=(True,)).start()
            return

        log = self.log

        class AuthServer(BaseHTTPRequestHandler):
            def __init__(self, request, client_address, server: BaseServer) -> None:
                super().__init__(request, client_address, server)
                # Use a different attribute name to avoid clashing with handler internals
                self._server_timeout = 50

            def do_GET(self):
                log(
                    "SERVER - Received GET request from address {}".format(
                        self.client_address
                    )
                )
                req = self.path.split("/")[1]
                args = {}
                for arg in req.split("?")[1:]:
                    a = arg.split("=")
                    if len(a) == 2:
                        args[a[0]] = a[1]
                if "code" in args.keys():
                    code = args["code"]
                    globals()["Auth_Code"] = code

                    self.send_response(200)
                    self.end_headers()
                    # self.wfile.write(bytes('<!DOCTYPE html><html><head><script type="text/javascript">function close_window(){window.close();}</script></head><body onload="close_window();"><p>WTF</p></body></html>', "utf-8"))
                    self.wfile.write(bytes("OK", "utf-8"))
                else:
                    self.wfile.write(bytes("Error", "utf-8"))

        code = secrets.token_urlsafe(100)[:128]
        url = f"https://myanimelist.net/v1/oauth2/authorize?response_type=code&client_id={self.CLIENT_ID}&code_challenge={code}"
        webbrowser.open(url)

        authServ = HTTPServer((self.hostName, self.serverPort), AuthServer)
        authorisation_code = None
        start = time.time()
        while time.time() < start + 10 * 60:
            authServ.handle_request()
            if "Auth_Code" in globals().keys():
                authorisation_code = globals()["Auth_Code"]
                break

        if authorisation_code is None:
            # Timed out
            return

        url = "https://myanimelist.net/v1/oauth2/token"
        data = {
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "code": authorisation_code,
            "code_verifier": code,
            "grant_type": "authorization_code",
        }

        response = requests.post(url, data)
        response.raise_for_status()

        token = response.json()
        response.close()
        self.log("MAL token generated successfully!")

        with open(self.tokenPath, "w") as file:
            json.dump(token, file, indent=4)

        if not self.check_validity(token["access_token"]):
            return self.refresh_token(token["refresh_token"])

        return token

    def refresh_token(self, r_token):
        url = "https://myanimelist.net/v1/oauth2/token"
        data = {
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": r_token,
        }

        try:
            response = requests.post(url, data)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            return

        token = response.json()
        response.close()
        self.log("MAL token refreshed successfully!")

        with open(self.tokenPath, "w") as file:
            json.dump(token, file, indent=4)

        return token

    def getToken(self):
        # Read token from tokenPath if present. Do not initiate interactive
        # authorization flow from here; that must be triggered explicitly by
        # calling getNewToken().
        if os.path.isfile(self.tokenPath):
            with open(self.tokenPath, "r") as file:
                token = json.load(file)

            # Validate and refresh if needed
            if not self.check_validity(token.get("access_token")):
                try:
                    token = self.refresh_token(token.get("refresh_token"))
                except Exception:
                    return None
            if token is not None:
                return token.get("access_token")
            return None
        else:
            # No token file present; do not attempt interactive auth here
            return None
