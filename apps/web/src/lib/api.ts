import type { Resource } from "@lonora/contracts";
import { ReadRequestGate } from "@lonora/core";

export type * from "@lonora/contracts";
export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
  ) {
    super(code);
  }
}
export class RequestCancelled extends Error {
  readonly code = "request_cancelled";
  constructor() {
    super("request_cancelled");
    this.name = "AbortError";
  }
}
export function isRequestCancelled(error: unknown) {
  return (
    error instanceof RequestCancelled || (error instanceof Error && error.name === "AbortError")
  );
}
let sessionGeneration = 0;
const active = new Map<AbortController, boolean>();
const pendingReads = new Map<string, Promise<unknown>>();
const reads = new ReadRequestGate();
export function resetSessionRequests() {
  sessionGeneration += 1;
  for (const controller of active.keys()) controller.abort();
  active.clear();
  pendingReads.clear();
  window.dispatchEvent(new Event("lonora:session-reset"));
}
// Leaving/backgrounding a page is not a failed user operation. Writes retain
// their actual outcome; only read projections are cancelled and reconciled on return.
if (typeof document !== "undefined")
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden")
      for (const [controller, read] of active) if (read) controller.abort();
  });
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
async function perform<T>(path: string, init: RequestInit): Promise<T> {
  const generation = sessionGeneration;
  const controller = new AbortController();
  const read = !init.method || ["GET", "HEAD"].includes(init.method);
  // Initial authentication must still finish when a tab first opens in the background.
  active.set(controller, read && !path.startsWith("/auth/") && !path.startsWith("/onboarding"));
  const abort = () => controller.abort();
  init.signal?.addEventListener("abort", abort, { once: true });
  if (init.signal?.aborted) controller.abort();
  const current = () => {
    if (generation !== sessionGeneration || controller.signal.aborted) throw new RequestCancelled();
  };
  let releaseRead: (() => void) | undefined;
  try {
    current();
    if (read) {
      const admitted = reads.enter(controller.signal);
      releaseRead = typeof admitted === "function" ? admitted : await admitted;
    }
    current();
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body && !(init.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    if (init.method && !["GET", "HEAD"].includes(init.method))
      headers.set("X-CSRF-Token", decodeURIComponent(csrfToken()));
    const response = await fetch(`/api${path}`, {
      ...init,
      signal: controller.signal,
      headers,
      credentials: "include",
      priority: read ? "low" : "high",
    });
    current();
    if (!response.ok) {
      const data = await response.json().catch(() => ({ code: "request_failed" }));
      current();
      if (response.status === 401 && !path.startsWith("/auth/"))
        window.dispatchEvent(new CustomEvent("lonora:session-expired"));
      throw new ApiError(data.code ?? "request_failed", response.status);
    }
    const data = await response.json();
    current();
    return data as T;
  } catch (error) {
    current();
    throw error;
  } finally {
    releaseRead?.();
    active.delete(controller);
    init.signal?.removeEventListener("abort", abort);
  }
}
export function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (init.signal || (init.method && init.method !== "GET")) return perform<T>(path, init);
  const key = `${sessionGeneration}:${path}`;
  const pending = pendingReads.get(key);
  if (pending) return pending as Promise<T>;
  const promise = perform<T>(path, init).finally(() => {
    if (pendingReads.get(key) === promise) pendingReads.delete(key);
  });
  pendingReads.set(key, promise);
  return promise;
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
