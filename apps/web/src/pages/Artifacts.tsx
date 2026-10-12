// Adapted for Lonora from Tampletgrok Artifacts.tsx (Apache-2.0).
import { Trans, useLingui } from "@lingui/react/macro";
import { Download, FileText, Filter, Image, LayoutGrid, List, Search, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FilePreviewPanel } from "../components/common/FilePreviewPanel";
import { api, type Resource } from "../lib/api";
import { artifacts, artifactUrl } from "../lib/artifacts";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";

type ViewMode = "grid" | "list";
type DateFilter = "all" | "today" | "week" | "month";
const viewModeKey = "lonora:artifacts-view-mode";
function readViewMode(): ViewMode {
  try {
    return localStorage.getItem(viewModeKey) === "list" ? "list" : "grid";
  } catch {
    return "grid";
  }
}
function matchesDate(iso: string, filter: DateFilter, now: Date): boolean {
  if (filter === "all") return true;
  const date = new Date(iso);
  if (filter === "today") return date.toDateString() === now.toDateString();
  if (filter === "week") {
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    start.setDate(start.getDate() - start.getDay());
    return date >= start;
  }
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth();
}
function filename(artifact: Resource) {
  return String(artifact.payload.filename ?? artifact.payload.name ?? artifact.id);
}
function mimeType(artifact: Resource) {
  return String(artifact.payload.media_type ?? artifact.payload.mime_type ?? "");
}

export function Artifacts() {
  const { t } = useLingui();
  const { revision, refresh } = useClient();
  const { artifactId } = useParams<{ artifactId?: string }>();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Resource[] | null>(null);
  const [preview, setPreview] = useState<Resource | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<unknown>();
  const [previewError, setPreviewError] = useState<unknown>();
  const [uploading, setUploading] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>(readViewMode);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void revision;
    let active = true;
    void artifacts
      .list()
      .then((items) => {
        if (active) {
          setRows(items);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (active) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [revision]);

  useEffect(() => {
    if (!artifactId) {
      setPreview(null);
      setPreviewError(undefined);
      setPreviewLoading(false);
      return;
    }
    const current = rows?.find((entry) => entry.id === artifactId);
    if (current) {
      setPreview(current);
      setPreviewLoading(false);
      setPreviewError(undefined);
      return;
    }
    let active = true;
    setPreviewLoading(true);
    setPreviewError(undefined);
    void api
      .get<Resource>(`/artifacts/${encodeURIComponent(artifactId)}`)
      .then((item) => {
        if (active) setPreview(item);
      })
      .catch((cause) => {
        if (active) setPreviewError(cause);
      })
      .finally(() => {
        if (active) setPreviewLoading(false);
      });
    return () => {
      active = false;
    };
  }, [artifactId, rows]);

  const filtered = useMemo(() => {
    const now = new Date();
    const term = query.trim().toLocaleLowerCase();
    return (
      rows?.filter(
        (item) =>
          matchesDate(item.created_at, dateFilter, now) &&
          (!term ||
            filename(item).toLocaleLowerCase().includes(term) ||
            String(item.payload.description ?? "")
              .toLocaleLowerCase()
              .includes(term)),
      ) ?? []
    );
  }, [rows, query, dateFilter]);

  function setMode(mode: ViewMode) {
    setViewMode(mode);
    try {
      localStorage.setItem(viewModeKey, mode);
    } catch {
      /* Display preference only. */
    }
  }

  return (
    <section className="workspace-surface" data-testid="workspace-artifacts">
      <header className="workspace-surface-header">
        <div className="workspace-surface-heading">
          <h1>
            <Trans>Artifacts</Trans>
          </h1>
          <p>
            <Trans>Files and outputs from your agents will appear here.</Trans>
          </p>
        </div>
        <div className="workspace-surface-actions">
          <button
            type="button"
            className="workspace-button"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((open) => !open)}
          >
            <Filter size={15} aria-hidden="true" />
            <Trans>Filters</Trans>
          </button>
          <div className="workspace-view-switch">
            <button
              type="button"
              className="workspace-icon-button"
              aria-pressed={viewMode === "grid"}
              aria-label={t`Card view`}
              onClick={() => setMode("grid")}
            >
              <LayoutGrid size={16} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="workspace-icon-button"
              aria-pressed={viewMode === "list"}
              aria-label={t`List view`}
              onClick={() => setMode("list")}
            >
              <List size={16} aria-hidden="true" />
            </button>
          </div>
          <button
            type="button"
            className="workspace-button workspace-button-primary"
            disabled={uploading}
            onClick={() => input.current?.click()}
          >
            <Upload size={15} aria-hidden="true" />
            {uploading ? <Trans>Uploading…</Trans> : <Trans>Upload file</Trans>}
          </button>
          <input
            ref={input}
            type="file"
            hidden
            multiple
            onChange={async (event) => {
              const files = Array.from(event.target.files ?? []);
              event.target.value = "";
              if (!files.length) return;
              setUploading(true);
              setError(undefined);
              try {
                const results = await Promise.allSettled(files.map((file) => api.upload(file)));
                const failed = results.find((entry) => entry.status === "rejected");
                if (failed?.status === "rejected") setError(failed.reason);
                refresh();
              } finally {
                setUploading(false);
              }
            }}
          />
        </div>
      </header>
      {filtersOpen && (
        <div className="workspace-artifact-filters">
          <label className="workspace-search-field">
            <span className="sr-only">
              <Trans>Search artifacts</Trans>
            </span>
            <Search size={16} aria-hidden="true" />
            <input
              type="search"
              value={query}
              placeholder={t`Search artifacts…`}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <label className="workspace-inline-label">
            <span className="sr-only">
              <Trans>Filter by date</Trans>
            </span>
            <select
              aria-label={t`Filter by date`}
              value={dateFilter}
              onChange={(event) => setDateFilter(event.target.value as DateFilter)}
            >
              <option value="all">
                <Trans>All time</Trans>
              </option>
              <option value="today">
                <Trans>Today</Trans>
              </option>
              <option value="week">
                <Trans>This week</Trans>
              </option>
              <option value="month">
                <Trans>This month</Trans>
              </option>
            </select>
          </label>
        </div>
      )}
      {error != null && (
        <div className="workspace-error" role="alert">
          <p>{userError(error)}</p>
          <button type="button" className="workspace-button" onClick={refresh}>
            <Trans>Retry</Trans>
          </button>
        </div>
      )}
      {previewError != null && (
        <div className="workspace-error" role="alert">
          <p>{userError(previewError)}</p>
          <button
            type="button"
            className="workspace-button"
            onClick={() => navigate("/app/artifacts", { replace: true })}
          >
            <Trans>Back to artifacts</Trans>
          </button>
        </div>
      )}
      <div className="workspace-surface-body" aria-busy={rows === null || uploading}>
        {rows === null ? (
          error == null && (
            <p className="workspace-empty" role="status">
              <Trans>Loading…</Trans>
            </p>
          )
        ) : !filtered.length ? (
          <div className="workspace-empty">
            <FileText size={28} aria-hidden="true" />
            <p>
              {query.trim() || dateFilter !== "all" ? (
                <Trans>No matching artifacts</Trans>
              ) : (
                <Trans>No artifacts found.</Trans>
              )}
            </p>
          </div>
        ) : (
          <div
            className={viewMode === "grid" ? "workspace-artifact-grid" : "workspace-artifact-list"}
          >
            {filtered.map((artifact) => (
              <article className="workspace-artifact-card" key={artifact.id}>
                <button
                  className="workspace-artifact-open"
                  type="button"
                  onClick={() => navigate(`/app/artifacts/${artifact.id}`)}
                >
                  <span className="workspace-artifact-icon">
                    {mimeType(artifact).startsWith("image/") ? (
                      <Image size={21} aria-hidden="true" />
                    ) : (
                      <FileText size={21} aria-hidden="true" />
                    )}
                  </span>
                  <span className="workspace-artifact-details">
                    <strong>
                      <bdi>{filename(artifact)}</bdi>
                    </strong>
                    {artifact.payload.description && (
                      <span dir="auto">{String(artifact.payload.description)}</span>
                    )}
                    <small>
                      <bdi>{Number(artifact.payload.size ?? 0).toLocaleString()}</bdi>{" "}
                      <Trans>bytes</Trans>
                      <span aria-hidden="true"> · </span>
                      <time dateTime={artifact.created_at}>
                        {new Date(artifact.created_at).toLocaleDateString()}
                      </time>
                    </small>
                  </span>
                  <span className="workspace-mime-label">
                    <bdi>{mimeType(artifact).split("/").at(-1) || "—"}</bdi>
                  </span>
                </button>
                <a className="workspace-artifact-download" href={artifactUrl(artifact.id)}>
                  <Download size={14} aria-hidden="true" />
                  <Trans>Download</Trans>
                </a>
              </article>
            ))}
          </div>
        )}
        {previewLoading && (
          <p className="workspace-preview-loading" role="status">
            <Trans>Loading preview…</Trans>
          </p>
        )}
      </div>
      {artifactId && preview?.id === artifactId && (
        <FilePreviewPanel
          artifact={preview}
          historyManaged={false}
          onClose={() => navigate("/app/artifacts", { replace: true })}
        />
      )}
    </section>
  );
}
