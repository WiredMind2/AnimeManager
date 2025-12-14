# from .nova3.custom_engine import search # TODO - Fix it first

import os
import queue
import re
import subprocess
import sys
import threading


def search(terms):
    # Since I'm very smart, I've decided that instead of fixing the problem between Apache, WSGI, Flask and multiprocessing.Manager wasn't worth it.
    # So here I am, running a python script from the cmd, from another python script, specifically from a function hidden in a __init__ file that I'm
    # DEFINITELY gonna forget about. Good luck, future me...

    keys = ["link", "name", "size", "seeds", "leech", "engine_url", "desc_link"]
    mag_reg = re.compile(r"^magnet:\?xt=urn:\S+$")  # Only returns magnet links
    root = os.path.dirname(__file__)

    def wrapper(term, que):
        # command = f'python3 -m nova3.nova2 all anime "{term}"' # For linux only?
        exec_name = (
            "python3" if sys.platform == "linux" else f'"{sys.executable}"'
        )  # TODO - Full path for linux?
        command = f'{exec_name} -m nova3.nova2 all anime "{term}"'  # Don't ask why it's named like that, idk either
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            cwd=root,
        )
        while True:
            if process.stdout is None:
                break

            output = process.stdout.readline()
            if output == b"" and process.poll() is not None:
                break
            if output:
                data = output.decode(encoding="utf-8", errors="ignore").strip()
                if data:
                    data = data.split("|")
                    if len(data) > 1:
                        out = dict(zip(keys, data))
                        # yield out
                        if re.match(mag_reg, out["link"]):
                            que.put(out)

        que.put("STOP")

    que = queue.Queue()
    threads = []
    for term in terms:
        t = threading.Thread(target=wrapper, args=(term, que))
        threads.append(t)
        t.start()
    # return process.poll()
    while threads:
        data = que.get()
        if data == "STOP":
            threads = list(filter(lambda t: t.is_alive(), threads))
        else:
            yield data


# # Add serach engines:
# # https://www.shanaproject.com/ -> Require login and following stuff: wayyyy too complicated for now
if __name__ == "__main__":
    for data in search(["test", "fish"]):
        print(data)
