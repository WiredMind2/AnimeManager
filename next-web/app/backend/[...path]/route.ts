import { NextRequest, NextResponse } from "next/server";
import { getInternalBackendUrl } from "@/lib/config";
import { REQUEST_ID_HEADER } from "@/lib/api";
import { applyProxyClientIdentityHeaders } from "@/proxy";

/** Resume playback can block on ffmpeg segment materialization for up to ~3 minutes. */
const PROXY_TIMEOUT_MS = 240_000;
const SLOW_PROXY_MS = 2000;

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxyRequest(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  const backendPath = path.map(encodeURIComponent).join("/");
  const incoming = new URL(request.url);
  const target = `${getInternalBackendUrl()}/${backendPath}${incoming.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");
  applyProxyClientIdentityHeaders(request, headers);
  const requestId = headers.get(REQUEST_ID_HEADER) ?? crypto.randomUUID();
  headers.set(REQUEST_ID_HEADER, requestId);

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), PROXY_TIMEOUT_MS);
  const started = performance.now();
  try {
    const response = await fetch(target, { ...init, signal: controller.signal });
    const elapsedMs = performance.now() - started;
    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("transfer-encoding");
    responseHeaders.set(REQUEST_ID_HEADER, response.headers.get(REQUEST_ID_HEADER) ?? requestId);
    if (elapsedMs >= SLOW_PROXY_MS) {
      console.warn(
        `[AnimeManager proxy] slow_proxy method=${request.method} path=/${backendPath} status=${response.status} duration_ms=${elapsedMs.toFixed(1)} request_id=${requestId}`,
      );
    }
    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (err) {
    const elapsedMs = performance.now() - started;
    const message = err instanceof Error ? err.message : "Backend proxy failed";
    console.error(
      `[AnimeManager proxy] proxy_failed method=${request.method} path=/${backendPath} duration_ms=${elapsedMs.toFixed(1)} request_id=${requestId} detail=${message}`,
    );
    return NextResponse.json(
      { detail: message, request_id: requestId },
      { status: 502, headers: { [REQUEST_ID_HEADER]: requestId } },
    );
  } finally {
    clearTimeout(timeout);
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const HEAD = proxyRequest;
export const OPTIONS = proxyRequest;
