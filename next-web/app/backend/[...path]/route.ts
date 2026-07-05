import { NextRequest, NextResponse } from "next/server";
import { getInternalBackendUrl } from "@/lib/config";

/** Resume playback can block on ffmpeg segment materialization for up to ~3 minutes. */
const PROXY_TIMEOUT_MS = 240_000;

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
  try {
    const response = await fetch(target, { ...init, signal: controller.signal });
    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("transfer-encoding");
    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Backend proxy failed";
    return NextResponse.json({ detail: message }, { status: 502 });
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
