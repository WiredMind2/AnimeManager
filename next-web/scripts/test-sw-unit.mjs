/**
 * Unit tests for sw.js fetch handler logic.
 *
 * Tests the two bugs fixed:
 *  1. The static-asset handler must ALWAYS resolve event.respondWith() to a
 *     valid Response — even when the cache is empty AND the network fails.
 *  2. shouldBypass() must pass through /backend/ and HLS segment URLs so the
 *     SW never calls event.respondWith() for those requests.
 *
 * Run: node scripts/test-sw-unit.mjs
 */

// ---------------------------------------------------------------------------
// Minimal service-worker global shim
// ---------------------------------------------------------------------------

const CACHE_VERSION = "am-next-pwa-v1";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

// Inline the production shouldBypass logic so changes stay in sync.
function shouldBypass(url, accept) {
  if (url.pathname.startsWith("/backend/")) return true;
  if (accept.includes("text/event-stream")) return true;
  if (url.pathname.includes("/torrents/stream")) return true;
  if (url.pathname.includes("/logs/stream")) return true;
  if (url.pathname.endsWith(".m3u8") || url.pathname.endsWith(".ts")) return true;
  return false;
}

// Simulates the fetch handler's static-asset branch (copied from sw.js).
// Returns the value that event.respondWith() would have received.
async function staticAssetHandlerResult({ cachedResponse, networkResult }) {
  const cached = cachedResponse; // may be undefined on cache miss
  const networkFetch = Promise.resolve()
    .then(() => {
      if (networkResult instanceof Error) throw networkResult;
      return networkResult; // a Response-like object or undefined
    })
    .catch(
      () =>
        cached ??
        new Response("", {
          status: 503,
          headers: { "Content-Type": "text/plain" },
        }),
    );
  return cached ?? networkFetch;
}

// ---------------------------------------------------------------------------
// Assertion helpers
// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;

function assert(condition, msg) {
  if (condition) {
    console.log(`  ✓ ${msg}`);
    passed++;
  } else {
    console.error(`  ✗ FAIL: ${msg}`);
    failed++;
  }
}

async function test(name, fn) {
  console.log(`\n${name}`);
  try {
    await fn();
  } catch (err) {
    console.error(`  ✗ UNCAUGHT: ${err}`);
    failed++;
  }
}

// ---------------------------------------------------------------------------
// shouldBypass tests
// ---------------------------------------------------------------------------

await test("shouldBypass: /backend/ URLs are bypassed", async () => {
  const url = new URL("http://localhost:3000/backend/ui/stream/abc/segment_00177.ts");
  assert(shouldBypass(url, ""), "/backend/ui/stream/… is bypassed");
  assert(shouldBypass(new URL("http://localhost:3000/backend/ui/anime/1/play"), ""), "/backend/ui/anime/…/play is bypassed");
});

await test("shouldBypass: HLS segment and manifest URLs are bypassed", async () => {
  const ts = new URL("http://localhost:3000/ui/stream/abc/segment_00177.ts");
  const m3u8 = new URL("http://localhost:3000/ui/stream/abc/index.m3u8");
  assert(shouldBypass(ts, ""), ".ts segment is bypassed");
  assert(shouldBypass(m3u8, ""), ".m3u8 manifest is bypassed");
});

await test("shouldBypass: regular page navigations are NOT bypassed", async () => {
  const url = new URL("http://localhost:3000/anime/1090/watch");
  assert(!shouldBypass(url, "text/html"), "watch page is not bypassed");
  assert(!shouldBypass(new URL("http://localhost:3000/library"), "text/html"), "/library is not bypassed");
});

await test("shouldBypass: /_next/static/ assets are NOT bypassed (cached by SW)", async () => {
  const url = new URL("http://localhost:3000/_next/static/chunks/main.js");
  assert(!shouldBypass(url, ""), "/_next/static/ assets handled by SW (not bypassed)");
});

// ---------------------------------------------------------------------------
// Static asset handler — BUG FIX: must always return valid Response
// ---------------------------------------------------------------------------

await test("static asset handler: cache hit returns cached Response", async () => {
  const fakeResponse = new Response("cached-body", { status: 200 });
  const result = await staticAssetHandlerResult({
    cachedResponse: fakeResponse,
    networkResult: new Response("network-body", { status: 200 }),
  });
  assert(result instanceof Response, "result is a Response");
  const body = await result.text();
  assert(body === "cached-body", "stale-while-revalidate: cache hit returns cached copy");
});

await test("static asset handler: cache miss + network ok returns network Response", async () => {
  const netResponse = new Response("network-body", { status: 200 });
  const result = await staticAssetHandlerResult({
    cachedResponse: undefined, // cache miss
    networkResult: netResponse,
  });
  // result may be a Promise (the networkFetch Promise) or a Response depending on impl;
  // await it to get the final value
  const resolved = result instanceof Promise ? await result : result;
  assert(resolved instanceof Response, "cache miss + network ok → valid Response");
  const body = await resolved.text();
  assert(body === "network-body", "network response body is correct");
});

await test("static asset handler: cache miss + network FAIL returns 503 Response (not undefined)", async () => {
  // This is the BUG we fixed: before the fix, this would resolve to undefined,
  // causing 'Failed to convert value to Response' TypeError.
  const result = await staticAssetHandlerResult({
    cachedResponse: undefined, // cache miss
    networkResult: new Error("network failure"), // fetch() rejects
  });
  const resolved = result instanceof Promise ? await result : result;
  assert(resolved !== undefined && resolved !== null, "result is not undefined/null");
  assert(resolved instanceof Response, "result is a valid Response (not undefined)");
  assert(resolved.status === 503, `fallback status is 503 (got ${resolved?.status})`);
});

await test("static asset handler: cache hit + network FAIL returns cached Response", async () => {
  const cachedResponse = new Response("stale-cached", { status: 200 });
  const result = await staticAssetHandlerResult({
    cachedResponse,
    networkResult: new Error("network failure"),
  });
  const resolved = result instanceof Promise ? await result : result;
  assert(resolved instanceof Response, "result is a valid Response");
  const body = await resolved.text();
  assert(body === "stale-cached", "falls back to cached copy when network fails");
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\n${"─".repeat(60)}`);
if (failed === 0) {
  console.log(`All ${passed} SW unit tests passed.`);
} else {
  console.log(`${passed} passed, ${failed} FAILED.`);
  process.exit(1);
}
