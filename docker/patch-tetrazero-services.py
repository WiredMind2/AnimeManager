#!/usr/bin/env python3
from pathlib import Path

p = Path("/home/william/TetrazeroDashboard/services.yaml")
text = p.read_text()

old = "      - hostname: anime.tetrazero.com\n        port: 8001\n"
if old in text:
    text = text.replace(old, "")
else:
    print("WARN: anime route block not found")

insert_after = """    hostname: bobst.tetrazero.com
    group: apps

"""
new_block = """    hostname: bobst.tetrazero.com
    group: apps

  animemanager:
    label: AnimeManager
    path: /home/william/AnimeManager
    compose_files: [docker-compose.yml]
    autostart: true
    startup_order: 10
    port: 3010
    hostname: anime.tetrazero.com
    group: apps
    notes: Docker stack; web on 3010, Kibana internal 5601

  animemanager_observability:
    label: AnimeManager Observability
    path: /home/william/AnimeManager
    autostart: false
    port: 5601
    hostname: observability.tetrazero.com
    group: apps
    notes: Kibana only; proxied from Docker bind 127.0.0.1:5601

"""

if "animemanager:" not in text:
    if insert_after not in text:
        raise SystemExit("insert anchor not found")
    text = text.replace(insert_after, new_block, 1)
else:
    print("animemanager already present")

p.write_text(text)
print("services.yaml updated")
