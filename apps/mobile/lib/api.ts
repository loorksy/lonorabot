import type { Artifact } from "@lonora/contracts";
import { attachmentTooLarge, ReadRequestGate } from "@lonora/core";
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
const reads = new ReadRequestGate();

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
  let releaseRead: (() => void) | undefined;
  try {
    assertCurrent();
    if (!init.method || ["GET", "HEAD"].includes(init.method)) {
      const admitted = reads.enter(controller.signal);
      releaseRead = typeof admitted === "function" ? admitted : await admitted;
    }
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
    releaseRead?.();
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

/**
 * One picked file's upload with its progress (0..1) and a cancel, for the composer's ring.
 * XMLHttpRequest because fetch reports no upload progress; the session's credentials and the
 * sign-out fence are the same as every other request's.
 */
export function uploadTransfer(asset: DocumentPickerAsset, threadId: string) {
  return async (progress: (p: number) => void, signal: AbortSignal): Promise<Artifact> => {
    if (attachmentTooLarge(asset.size)) throw new ApiError("attachment_too_large", 400);
    const requestGeneration = generation;
    const body = new FormData();
    if (Platform.OS === "web") {
      const file = asset.file ?? (await (await fetch(asset.uri)).blob());
      body.append("file", file, asset.name);
    } else {
      body.append("file", {
        uri: asset.uri,
        name: asset.name,
        type: asset.mimeType ?? "application/octet-stream",
      } as unknown as Blob);
    }
    body.append("thread_id", threadId);
    return new Promise<Artifact>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const current = () => requestGeneration === generation && !signal.aborted;
      xhr.open("POST", `${base}/api/artifacts/upload`);
      xhr.withCredentials = true;
      xhr.setRequestHeader("Accept", "application/json");
      if (bearer) xhr.setRequestHeader("Authorization", `Bearer ${bearer}`);
      else xhr.setRequestHeader("X-CSRF-Token", browserCsrf());
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && current()) progress(event.loaded / event.total);
      };
      xhr.onload = () => {
        if (!current()) return reject(new SessionRequestCancelled());
        let data: { code?: string } & Partial<Artifact> = {};
        try {
          data = JSON.parse(xhr.responseText || "{}");
        } catch {
          /* A proxy's HTML page is not Lonora's answer. */
        }
        if (xhr.status >= 200 && xhr.status < 300) return resolve(data as Artifact);
        if (xhr.status === 401) expired?.();
        reject(new ApiError(data.code ?? "request_failed", xhr.status));
      };
      xhr.onerror = () => reject(new TypeError("Network request failed"));
      xhr.onabort = () => reject(new SessionRequestCancelled());
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
      xhr.send(body);
    });
  };
}
