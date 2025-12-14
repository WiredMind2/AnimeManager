import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from .getters import Getters
    from .logger import log
except ImportError:
    from getters import Getters
    from logger import log


def startServer(hostName, serverPort, manager):
    def serve_thread(webServer):
        try:
            webServer.serve_forever()
        except OSError:
            pass

    handler = GetHandler(manager)
    httpd = HTTPServer((hostName, serverPort), handler)
    keyFile, certFile = "./key.pem", "./cert.pem"
    usessl = os.path.exists(keyFile) and os.path.exists(certFile)
    if usessl:
        httpd.socket = ssl.wrap_socket(
            httpd.socket, keyfile="./key.pem", certfile="./cert.pem", server_side=True
        )

    manager.log(
        "SERVER",
        "Server started http%s://%s:%s" % ("s" if usessl else "", hostName, serverPort),
    )

    # webServer.serve_forever()
    t = threading.Thread(target=serve_thread, args=(httpd,), daemon=True)
    t.start()

    return httpd


def stopServer(webServer, manager):
    webServer.server_close()
    manager.log("SERVER", "Server stopped.")


def GetHandler(manager):
    class DbServer(BaseHTTPRequestHandler, Getters):
        def do_GET(self):
            code = 200
            content = "application/json"

            self.database = self.getDatabase()
            log(
                "SERVER",
                "Received GET request from address {}".format(self.client_address),
            )
            request = self.path.split("/")[1:]
            if request[0] != "":
                table = request.pop(0)
                if len(request) >= 1:
                    id = request.pop(0)
                else:
                    id = None
            else:
                table = None
                id = None

            if table is not None:
                if table == "sync":
                    data = self.getAnimesToSync()
                    content = "application/json"
                elif id is not None:
                    data = self.database(id=id, table=table)
                    if data["id"] == "NONE":
                        # data = "404 - Id not in db"
                        # code = 404
                        # content = "text/plain"
                        self.send_error(
                            400,
                            "Id not in db",
                            "The id {} is not in the database.".format(id),
                        )
                        return
                else:
                    try:
                        data = dict(self.database.sql("SELECT * FROM {}".format(table)))
                    except Exception:
                        code = 404
                        content = "text/html; charset=UTF-8"
                        data = "404 - Invalid table"

            else:
                content = "text/html;charset='utf-8'"
                data = "<!DOCTYPE html><html><header><meta charset='utf-8'><title>Heyyy</title><body><h1>Main page</h1><p>I need something here</p></body></html>"

            self.send_response(code)
            self.send_header("Content-type", content)
            self.end_headers()
            self.send(data, content)

        def do_POST(self):
            length = int(self.headers["Content-length"])
            rep = json.loads(self.rfile.read(length))
            log(
                "SERVER",
                "Received sync request (POST) from address {}, {} animes.".format(
                    self.client_address, len(rep)
                ),
            )
            self.saveAnimes(rep)
            self.send_response(200, "OK")
            self.end_headers()

            rep = self.getAnimesToSync()

            self.send(rep, "application/json")
            # self.wfile.write(bytes(json.dumps(rep),"utf-8"))

        def saveAnimes(self, rep):
            self.database = self.getDatabase()
            self.manager = manager
            for anime in rep:
                id, tag, like = anime.values()
                if not self.database.exist(id=id, table="anime"):  # Deprecated
                    try:
                        log("SERVER", "Fetching data for id", id)
                        data = self.manager.getData(id)
                        data["id"] = id  # TODO - Needed?
                        self.database.set(
                            data, table="anime", save=False, get_output=False
                        )
                    except Exception:
                        pass

            self.database.save()

        def getAnimesToSync(self):
            self.database = self.getDatabase()
            content = self.database.sql(
                """SELECT
                    anime.id,
                    title,
                    title_synonyms,
                    picture,
                    synopsis,
                    episodes,
                    duration,
                    rating,
                    status,
                    broadcast,
                    trailer,
                    like,
                    tag
                FROM anime
                WHERE tag in ("WATCHLIST","WATCHING","SEEN")
            """
            )
            rep = []
            keys = (
                "mal_id",
                "title",
                "title_synonyms",
                "image_url",
                "synopsis",
                "episodes",
                "duration",
                "rating",
                "status",
                "broadcast",
                "trailer_url",
                "tag",
                "like",
            )

            for c in content:
                value = dict(zip(keys, c))
                rep.append(value)

            return rep

        def send(self, data, content):
            if content == "application/json":
                data = json.dumps(data)
            self.wfile.write(bytes(data, "utf-8"))

    return DbServer
