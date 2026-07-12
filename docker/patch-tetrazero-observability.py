#!/usr/bin/env python3
"""Update TetrazeroDashboard services.yaml for split observability stack."""
from pathlib import Path

p = Path("/home/william/TetrazeroDashboard/services.yaml")
text = p.read_text()

# Remove animemanager_observability block if present
start = "  animemanager_observability:"
if start in text:
    lines = text.splitlines(keepends=True)
    out = []
    skip = False
    for line in lines:
        if line.startswith("  animemanager_observability:"):
            skip = True
            continue
        if skip:
            if line.startswith("  ") and not line.startswith("    ") and not line.startswith("  animemanager_observability"):
                skip = False
            else:
                continue
        out.append(line)
    text = "".join(out)

obs_block = """  observability:
    label: Observability (Elastic)
    path: /home/william/tetrazero-observability
    compose_files: [docker-compose.yml]
    autostart: true
    startup_order: 5
    port: 5601
    hostname: observability.tetrazero.com
    group: infrastructure
    notes: Shared ES/Kibana/OTLP stack

"""

if "  observability:" not in text or "tetrazero-observability" not in text:
    anchor = "  animemanager:\n"
    if anchor not in text:
        raise SystemExit("animemanager anchor not found")
    text = text.replace(anchor, obs_block + anchor, 1)

# Update animemanager notes
text = text.replace(
    "notes: Docker stack; web on 3010, Kibana internal 5601",
    "notes: Docker app stack; joins network tetrazero-observability",
)

p.write_text(text)
print("services.yaml updated")
