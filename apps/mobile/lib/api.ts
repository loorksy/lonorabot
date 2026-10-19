import type { Artifact } from "@lonora/contracts";
import { attachmentTooLarge } from "@lonora/core";
import type { DocumentPickerAsset } from "expo-document-picker";
import { Platform } from "react-native";
import { ApiError } from "./api-error";

export { ApiError } from "./api-error";

let base = Platform.OS === "web" && typeof window !== "undefined" ? window.location.origin : "";
let bearer: string | null = null;
let csrf = "";
let expired: (() => void) | null = null;
let generation = 0;
const pending = new Set<{ controller: AbortController; readOnly: boolean; cancelled: boolean }>();

// Cancellation is lifecycle state, not an unsuccessful server response.
export class SessionRequestCancelled extends Error {
  constructor() {
    super("session_request_cancelled");
    this.name = "SessionRequestCancelled";
  }
}
export function cancelSessionRequests() {
  generation += 1;
  for (const request of pending) {
    request.cancelled = true;
    request.controller.abort();
  }
}
export function cancelBackgroundReads() {
  for (const request of pending) {
    if (!request.readOnly) continue;
    request.cancelled = true;
    request.controller.abort();
  }
}

async function sessionFetch<T>(
  path: string,
  init: RequestInit,
  consume: (response: Response) => Promise<T>,
): Promise<T> {
  const requestGeneration = generation;
  const controller = new AbortController();
  const entry = {
    controller,
    readOnly:
      (!init.method || ["GET", "HEAD"].includes(init.method)) &&
      !path.startsWith("/auth/") &&
      !path.startsWith("/onboarding"),
    cancelled: false,
  };
  const cancel = () => {
    entry.cancelled = true;
    controller.abort();
  };
  const assertCurrent = () => {
    if (entry.cancelled || requestGeneration !== generation) throw new SessionRequestCancelled();
  };
  pending.add(entry);
  init.signal?.addEventListener("abort", cancel, { once: true });
  if (init.signal?.aborted) cancel();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  try {
    assertCurrent();
    const response = await fetch(`${base}/api${path}`, {
      ...init,
      credentials: "include",
      signal: controller.signal,
    });
    assertCurrent();
    if (!response.ok) {
      const data = await response.json().catch(() => ({ code: "request_failed" }));
      assertCurrent();
      if (response.status === 401 && !path.startsWith("/auth/")) expired?.();
      assertCurrent();
      throw new ApiError(data.code ?? "request_failed", response.status);
    }
    const value = await consume(response);
    assertCurrent();
    return value;
  } catch (error) {
    assertCurrent();
    throw error;
  } finally {
    clearTimeout(timeout);
    pending.delete(entry);
    init.signal?.removeEventListener("abort", cancel);
  }
}

export function normalizeServer(value: string): string {
  const url = new URL(value.trim());
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password)
    throw new ApiError("invalid_server", 0);
  if (url.search || url.hash) throw new ApiError("invalid_server", 0);
  return url
    .toString()
    .replace(/\/api\/?$/, "")
    .replace(/\/$/, "");
}

export function configureApi(server: string, token: string | null, onExpired: () => void) {
  cancelSessionRequests();
  base = normalizeServer(server);
  bearer = Platform.OS === "web" ? null : token;
  csrf = "";
  expired = onExpired;
}

export function setCredentials(token: string | null, csrfValue = "") {
  cancelSessionRequests();
  bearer = Platform.OS === "web" ? null : token;
  csrf = csrfValue;
}

function browserCsrf(): string {
  if (Platform.OS !== "web" || typeof document === "undefined") return "";
  const cookie = document.cookie.split("; ").find((item) => item.startsWith("lonora_csrf="));
  return cookie ? decodeURIComponent(cookie.slice("lonora_csrf=".length)) : csrf;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (bearer) headers.set("Authorization", `Bearer ${bearer}`);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (!bearer && init.method && !["GET", "HEAD"].includes(init.method))
    headers.set("X-CSRF-Token", browserCsrf());
  return sessionFetch(path, { ...init, headers }, (response) => response.json() as Promise<T>);
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
};

export async function getArtifactFile(
  id: string,
): Promise<{ bytes: Uint8Array; mediaType: string }> {
  const headers = new Headers();
  if (bearer) headers.set("Authorization", `Bearer ${bearer}`);
  return sessionFetch(
    `/artifacts/${encodeURIComponent(id)}/file`,
    { headers },
    async (response) => ({
      bytes: new Uint8Array(await response.arrayBuffer()),
      mediaType: response.headers.get("content-type")?.split(";")[0] ?? "application/octet-stream",
    }),
  );
}

export async function upload(asset: DocumentPickerAsset, threadId: string): Promise<Artifact> {
  if (attachmentTooLarge(asset.size)) throw new ApiError("attachment_too_large", 400);
  const body = new FormData();
  if (Platform.OS === "web") {
    const file = asset.file ?? (await (await fetch(asset.uri)).blob());
    body.append("file", file, asset.name);
  } else {
    // React Native FormData understands a local URI; browsers instead receive a real File/Blob.
    body.append("file", {
      uri: asset.uri,
      name: asset.name,
      type: asset.mimeType ?? "application/octet-stream",
    } as unknown as Blob);
  }
  body.append("thread_id", threadId);
  return request<Artifact>("/artifacts/upload", { method: "POST", body });
}
