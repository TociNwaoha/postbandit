import { getSession } from "next-auth/react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const PROXY_PREFIX = "/api/backend";

class ApiError extends Error {
  public detail?: unknown;
  public code?: string;

  constructor(
    public status: number,
    message: string,
    detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
    this.detail = detail;
    if (detail && typeof detail === "object" && "error" in detail) {
      this.code = String((detail as { error?: unknown }).error || "");
    }
  }
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const session = await getSession();
  const token = (session as any)?.accessToken;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const absoluteUrl = `${API_URL}${normalizedPath}`;
  const proxyUrl = `${PROXY_PREFIX}${normalizedPath.replace(/^\/api/, "")}`;

  const requestInit: RequestInit = {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...options.headers,
    },
  };

  let res: Response;
  try {
    res = await fetch(absoluteUrl, requestInit);
  } catch {
    // Fallback for browser/network/adblock issues on direct API domain:
    // use same-origin Next.js rewrite proxy path.
    res = await fetch(proxyUrl, requestInit);
  }

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Request failed" }));
    const detail = body.detail || "Request failed";

    // Backend auth dependency can return 403 for missing/invalid bearer token.
    // Treat this the same as 401 so stale client sessions recover predictably.
    if (
      res.status === 403 &&
      typeof window !== "undefined" &&
      typeof detail === "string" &&
      (detail.toLowerCase().includes("not authenticated") ||
        detail.toLowerCase().includes("invalid or expired token"))
    ) {
      window.location.href = "/login";
    }

    const message =
      detail && typeof detail === "object" && "message" in detail
        ? String((detail as { message?: unknown }).message || "Request failed")
        : String(detail || "Request failed");

    throw new ApiError(res.status, message, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  if (!text) {
    return undefined as T;
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    return text as T;
  }
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body: unknown) =>
    apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    apiFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    apiFetch<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: "DELETE" }),
};

export { ApiError };
