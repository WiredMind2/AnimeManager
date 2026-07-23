import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export const REQUEST_ID_HEADER = "x-request-id";

type NextRequestWithIp = NextRequest & { ip?: string | null };

/**
 * Resolve the browser/client IP for forwarding to the FastAPI backend.
 * Prefers upstream proxy headers, then Next.js request.ip when present.
 */
export function resolveProxyClientIp(request: NextRequest): string {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  if (forwarded) return forwarded;
  const realIp = request.headers.get("x-real-ip")?.trim();
  if (realIp) return realIp;
  const cfConnecting = request.headers.get("cf-connecting-ip")?.trim();
  if (cfConnecting) return cfConnecting;
  const ip = (request as NextRequestWithIp).ip;
  if (typeof ip === "string" && ip.trim()) return ip.trim();
  return "";
}

/**
 * Forward client identity headers so the FastAPI backend (playback LAN checks,
 * logging, etc.) sees the browser IP, not the Next.js server.
 */
export function applyProxyClientIdentityHeaders(
  request: NextRequest,
  headers: Headers,
): void {
  const clientIp = resolveProxyClientIp(request);
  if (clientIp) {
    headers.set("x-forwarded-for", clientIp);
    headers.set("x-real-ip", clientIp);
  }
  if (!headers.get(REQUEST_ID_HEADER)) {
    headers.set(REQUEST_ID_HEADER, crypto.randomUUID());
  }
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));
  headers.set("x-forwarded-host", request.headers.get("host") ?? request.nextUrl.host);
}

export function proxy(request: NextRequest) {
  if (!request.nextUrl.pathname.startsWith("/backend")) {
    return NextResponse.next();
  }

  const headers = new Headers(request.headers);
  applyProxyClientIdentityHeaders(request, headers);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/backend/:path*",
};
