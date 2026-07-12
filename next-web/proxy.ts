import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export const REQUEST_ID_HEADER = "x-request-id";

/**
 * Forward client identity headers so the FastAPI backend (playback LAN checks,
 * logging, etc.) sees the browser IP, not the Next.js server.
 */
export function proxy(request: NextRequest) {
  if (!request.nextUrl.pathname.startsWith("/backend")) {
    return NextResponse.next();
  }

  const headers = new Headers(request.headers);
  const clientIp =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    request.headers.get("x-real-ip") ||
    "";

  if (clientIp) {
    headers.set("x-forwarded-for", clientIp);
  }
  if (!headers.get(REQUEST_ID_HEADER)) {
    headers.set(REQUEST_ID_HEADER, crypto.randomUUID());
  }
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));
  headers.set("x-forwarded-host", request.headers.get("host") ?? request.nextUrl.host);

  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/backend/:path*",
};
