import type { Resource } from "@lonora/contracts";

export type * from "@lonora/contracts";
export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
  ) {
    super(code);
  }
}
export function csrfToken() {
  return (
    document.cookie
      .split("; ")
      .find((item) => item.startsWith("lonora_csrf="))
      ?.split("=")
      .slice(1)
      .join("=") ?? ""
  );
}
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method))
    headers.set("X-CSRF-Token", decodeURIComponent(csrfToken()));
  const response = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new CustomEvent("lonora:session-expired"));
    const data = await response.json().catch(() => ({ code: "request_failed" }));
    throw new ApiError(data.code ?? "request_failed", response.status);
  }
  return response.json() as Promise<T>;
}
export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: (file: File, threadId?: string) => {
    const data = new FormData();
    data.append("file", file);
    if (threadId) data.append("thread_id", threadId);
    return request<Resource>("/artifacts/upload", { method: "POST", body: data });
  },
};
