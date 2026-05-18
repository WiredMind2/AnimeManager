const API_BASE =
  process.env.PYTHON_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8081";

export function backendUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function backendFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(backendUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Backend ${response.status}: ${body}`);
  }
  return (await response.json()) as T;
}

export async function backendFetchHtml(
  path: string,
  init?: RequestInit,
): Promise<string> {
  const response = await fetch(backendUrl(path), {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "text/html",
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Backend ${response.status}: ${body}`);
  }
  return response.text();
}

export function browserWsBase(): string {
  if (typeof window === "undefined") return "";
  const configured = process.env.NEXT_PUBLIC_PYTHON_WS_BASE_URL?.replace(/\/+$/, "");
  if (configured) return configured;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}
