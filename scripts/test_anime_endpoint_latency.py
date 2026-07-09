"""Smoke-test anime detail endpoint latency against the running backend."""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8081"
GET_BUDGET_MS = 500
POST_BUDGET_MS = 500
POLL_BUDGET_MS = 500
REQUEST_TIMEOUT_S = 30
FALLBACK_IDS = [2210, 1908, 23, 1]


def call(method: str, path: str, timeout: float = REQUEST_TIMEOUT_S) -> tuple[float, dict]:
    req = urllib.request.Request(BASE + path, method=method)
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    elapsed_ms = (time.perf_counter() - start) * 1000
    payload = json.loads(body) if body else {}
    return elapsed_ms, payload


def ok(label: str, ms: float, budget: float) -> bool:
    status = "PASS" if ms <= budget else "FAIL"
    print(f"  [{status}] {label}: {ms:.1f}ms (budget {budget:.0f}ms)")
    return ms <= budget


def main() -> int:
    print("=== Anime detail endpoint latency ===")
    all_pass = True

    ids: list[int] = []
    try:
        list_ms, listing = call("GET", "/animelist?list_start=0&list_stop=5")
        print(f"  [INFO] GET /animelist sample: {list_ms:.1f}ms")
        all_pass &= ok("GET /animelist", list_ms, GET_BUDGET_MS)
        items = listing.get("items") or []
        ids = [int(item["id"]) for item in items[:3] if item.get("id")]
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"  [WARN] GET /animelist unavailable ({exc}); using fallback IDs")

    if not ids:
        ids = FALLBACK_IDS[:3]
    print(f"  [INFO] Testing anime IDs: {ids}")

    for anime_id in ids:
        print(f"\n-- anime {anime_id} --")

        get_ms, payload = call("GET", f"/anime/{anime_id}")
        all_pass &= ok(f"GET /anime/{anime_id}", get_ms, GET_BUDGET_MS)
        print(
            "       metadata_pending="
            f"{payload.get('metadata_pending')} "
            f"metadata_refreshing={payload.get('metadata_refreshing')}"
        )

        post_ms, accepted = call("POST", f"/anime/{anime_id}/refresh")
        all_pass &= ok(f"POST /anime/{anime_id}/refresh", post_ms, POST_BUDGET_MS)
        print(f"       accepted={accepted.get('accepted')}")

        poll_times: list[float] = []
        for index in range(3):
            time.sleep(0.25)
            ms, poll = call("GET", f"/anime/{anime_id}")
            poll_times.append(ms)
            all_pass &= ok(
                f"poll GET #{index + 1} /anime/{anime_id}",
                ms,
                POLL_BUDGET_MS,
            )
            _ = poll
        print(
            f"       poll median={statistics.median(poll_times):.1f}ms "
            f"max={max(poll_times):.1f}ms"
        )

        for suffix in ("characters", "pictures", "relations"):
            ms, _ = call("GET", f"/anime/{anime_id}/{suffix}")
            all_pass &= ok(f"GET /anime/{anime_id}/{suffix}", ms, GET_BUDGET_MS)

    print("\n=== Summary ===")
    if all_pass:
        print("All endpoint latency checks PASSED (no request exceeded budget).")
        return 0

    print("Some endpoint latency checks FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
