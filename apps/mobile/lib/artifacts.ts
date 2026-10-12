// Artifact cache/viewer lifecycle adapted from Tampletgrok's mobile artifact routes.
// See ../NOTICE. Fetches use the authenticated Lonora API; URLs never contain credentials.

import type { Artifact } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { Platform } from "react-native";
import { ApiError, api, getArtifactFile } from "./api";
import { useSession } from "./session";

export type ArtifactRecord = Artifact & {
  agent_id?: string | null;
  thread_id?: string | null;
  created_at?: string;
};
export type LoadedArtifact = {
  artifact: ArtifactRecord;
  mediaType: string;
  uri: string;
  text: string | null;
  truncated: boolean;
  share: () => Promise<void>;
  dispose: () => void;
};
const TEXT_PREVIEW_BYTES = 1024 * 1024;
const imageTypes = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

export function isImage(mediaType: string): boolean {
  return imageTypes.has(mediaType) || (Platform.OS === "web" && mediaType === "image/svg+xml");
}

export function isText(mediaType: string): boolean {
  return (
    mediaType.startsWith("text/") ||
    ["application/json", "application/xml", "application/yaml"].includes(mediaType)
  );
}

export function mimeBadge(mediaType: string): string {
  const value = mediaType.split(";")[0]?.split("/").at(-1) ?? "FILE";
  return value
    .replace(/^x-/, "")
    .replace(/\+xml$/, "")
    .toUpperCase();
}

export function formatFileSize(size: number, locale: string): string {
  const safe = Math.max(0, Number(size) || 0);
  if (safe < 1024) return `${new Intl.NumberFormat(locale).format(safe)} B`;
  const exponent = Math.min(Math.floor(Math.log(safe) / Math.log(1024)), 3);
  const unit = ["B", "KB", "MB", "GB"][exponent];
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(safe / 1024 ** exponent)} ${unit}`;
}

function cacheName(value: string): string {
  // The server owns the identifier; local cache names still exclude path separators.
  return value.replace(/[^\p{L}\p{N}._-]/gu, "_").slice(0, 120) || "artifact";
}

async function loadArtifact(id: string): Promise<LoadedArtifact> {
  const [artifact, content] = await Promise.all([
    api.get<ArtifactRecord>(`/artifacts/${encodeURIComponent(id)}`),
    getArtifactFile(id),
  ]);
  const mediaType = (artifact.payload.media_type || content.mediaType || "application/octet-stream")
    .split(";")[0]
    .toLowerCase();
  const previewBytes = content.bytes.subarray(0, TEXT_PREVIEW_BYTES);
  const truncated = content.bytes.byteLength > TEXT_PREVIEW_BYTES;
  const name = cacheName(artifact.payload.name || artifact.id);

  if (Platform.OS === "web") {
    const blob = new Blob([Uint8Array.from(content.bytes)], { type: mediaType });
    const uri = URL.createObjectURL(blob);
    const text = isText(mediaType) ? await new Blob([Uint8Array.from(previewBytes)]).text() : null;
    let disposed = false;
    return {
      artifact,
      mediaType,
      uri,
      text,
      truncated,
      share: async () => {
        if (disposed) return;
        const link = document.createElement("a");
        link.href = uri;
        link.download = name;
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
      },
      dispose: () => {
        disposed = true;
        URL.revokeObjectURL(uri);
      },
    };
  }

  const { Directory, File, Paths } = await import("expo-file-system");
  const directory = new Directory(
    Paths.cache,
    "lonora-artifacts",
    `${cacheName(id)}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  );
  directory.create({ intermediates: true });
  const file = new File(directory, name);
  try {
    file.create();
    file.write(content.bytes);
    let text: string | null = null;
    if (isText(mediaType)) {
      const preview = new File(directory, `.preview-${Math.random().toString(36).slice(2)}.txt`);
      preview.create();
      preview.write(previewBytes);
      text = await preview.text();
      preview.delete();
    }
    let disposed = false;
    let sharing = false;
    const cleanup = () => {
      try {
        if (!sharing && directory.exists) directory.delete();
      } catch {
        // Cache eviction must not crash navigation if the operating system already removed it.
      }
    };
    return {
      artifact,
      mediaType,
      uri: file.uri,
      text,
      truncated,
      share: async () => {
        if (disposed || sharing) return;
        const { isAvailableAsync, shareAsync } = await import("expo-sharing");
        if (!(await isAvailableAsync())) throw new ApiError("sharingUnavailable", 0);
        if (disposed || sharing) return;
        sharing = true;
        try {
          await shareAsync(file.uri, { mimeType: mediaType, dialogTitle: artifact.payload.name });
        } finally {
          sharing = false;
          if (disposed) cleanup();
        }
      },
      dispose: () => {
        disposed = true;
        cleanup();
      },
    };
  } catch (error) {
    if (directory.exists) directory.delete();
    throw error;
  }
}

export function useArtifact(id: string): {
  content: LoadedArtifact | null;
  error: string | null;
  loading: boolean;
  retry: () => void;
} {
  const { owner, ready, errorText } = useSession();
  const [content, setContent] = useState<LoadedArtifact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  // biome-ignore lint/correctness/useExhaustiveDependencies: An explicit retry refetches the same artifact identifier.
  useEffect(() => {
    if (!ready || !owner) return;
    let disposed = false;
    let loaded: LoadedArtifact | null = null;
    setContent(null);
    setError(null);
    setLoading(true);
    if (!id) {
      setError(errorText(new ApiError("fileMissing", 404)));
      setLoading(false);
      return;
    }
    void loadArtifact(id)
      .then((value) => {
        loaded = value;
        if (disposed) value.dispose();
        else setContent(value);
      })
      .catch((reason: unknown) => {
        if (!disposed) setError(errorText(reason));
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
      loaded?.dispose();
    };
  }, [id, ready, owner, revision, errorText]);
  return {
    content: content?.artifact.id === id ? content : null,
    error,
    loading,
    retry: () => setRevision((value) => value + 1),
  };
}

/** Sandboxing also applies to agent-created HTML; no script or external requests are enabled. */
export function isolatedHtml(source: string): string {
  const policy =
    "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'; object-src 'none'";
  return `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="${policy}"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{overflow-wrap:anywhere;margin:16px;color:#222;background:#fff;}</style></head><body>${source}</body></html>`;
}
