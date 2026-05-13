"""Tiny ad-hoc inspector for the sampled torrent titles."""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "scripts" / "_search_samples"

names: list[str] = []
for p in sorted(SAMPLES.glob("*.json")):
    if p.name.startswith("_"):
        continue
    with p.open("r", encoding="utf-8") as fh:
        for r in json.load(fh):
            n = r.get("name")
            if n:
                names.append(n)

def head(label: str) -> None:
    print(f"\n=== {label} ===")

# 1. Tail "-GROUP" or "-Group-Subs" detected
head("Tail-dash publishers (sample 20)")
pat = re.compile(r"-([A-Za-z][A-Za-z0-9_]{2,30}(?:-[A-Za-z][A-Za-z0-9_]{1,15})?)\s*(?:\[[0-9A-F]{6,8}\])?\s*(?:\.(?:mkv|mp4|avi))?\s*$")
hits = 0
for n in names:
    if re.match(r"^\s*\[", n):  # skip head-bracket ones
        continue
    m = pat.search(n)
    if m:
        hits += 1
        if hits <= 20:
            print(f"  -{m.group(1)} || {n}")
print(f"  total tail-dash hits: {hits}")

# 2. Chinese / 【】 publishers
head("CJK bracket publishers")
cjk = re.compile(r"^\s*[\[【]([^\]】]{1,40})[\]】]")
cjk_hits = 0
for n in names:
    if re.match(r"^\s*【", n):
        m = cjk.match(n)
        if m:
            cjk_hits += 1
            if cjk_hits <= 12:
                print(f"  {m.group(1)} || {n}")
print(f"  total: {cjk_hits}")

# 3. Sxx false-positive sanity check on Bocchi (only has S1 canonically)
head("Bocchi titles claiming S>=2")
with (SAMPLES / "bocchi_the_rock.json").open("r", encoding="utf-8") as fh:
    bocchi = json.load(fh)
sxx = re.compile(r"\bS(\d{1,2})(?:E\d{1,3})?\b")
counter = {}
for r in bocchi:
    n = r.get("name", "")
    m = sxx.search(n)
    if m and int(m.group(1)) >= 2:
        counter[int(m.group(1))] = counter.get(int(m.group(1)), 0) + 1
        if counter[int(m.group(1))] <= 2:
            print(f"  S{m.group(1)} || {n}")
print(f"  counts: {counter}")

# 4. Show some "messy" titles where everything is dot-separated (Scene style)
head("Scene-style dot separators")
scene = re.compile(r"^[A-Za-z0-9._-]+$")
shown = 0
for n in names:
    if "." in n and " " not in n and len(n) > 20:
        shown += 1
        if shown <= 10:
            print(f"  {n}")
print(f"  total: {shown}")

# 5. Compound season+episode: "S03E12", "S2 - 12", "Season 3 - 12"
head("Combined Season+Episode patterns")
combos = [
    re.compile(r"\bS(\d{1,2})E(\d{1,3})\b"),
    re.compile(r"\bSeason\s*(\d{1,2})\s*-\s*(\d{1,3})\b", re.I),
    re.compile(r"\b(\d{1,2})x(\d{2,3})\b"),
]
totals = [0] * len(combos)
for n in names:
    for i, p in enumerate(combos):
        if p.search(n):
            totals[i] += 1
            break
print(f"  SxxExx: {totals[0]}, Season N - M: {totals[1]}, NxMM: {totals[2]}")

# 6. Episode-range / batch indicators
head("Batch / range indicators")
batch = re.compile(r"\((\d{1,3})[\s.~_-]+(\d{1,3})\)|\b(\d{1,3})\s*~\s*(\d{1,3})\b|\b(\d{1,3})-(\d{1,3})\b|\bcomplete\b|\bbatch\b|\bseason\s*pack\b|\bbd[- ]?box\b", re.I)
cnt = 0
samples_shown = 0
for n in names:
    if batch.search(n):
        cnt += 1
        if samples_shown < 12:
            samples_shown += 1
            print(f"  {n}")
print(f"  total batch-ish: {cnt}")

# 7. CRC suffix detection [XXXXXXXX]
head("CRC checksum suffix")
crc = re.compile(r"\[[0-9A-F]{8}\]", re.I)
print(f"  count: {sum(1 for n in names if crc.search(n))}")

# 8. Multiple bracket tokens
head("Multi-bracket titles (very common with anime)")
multi = sum(1 for n in names if n.count("[") >= 3)
print(f"  titles with >=3 brackets: {multi}")
