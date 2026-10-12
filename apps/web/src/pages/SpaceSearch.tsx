// Adapted for Lonora from Tampletgrok SpaceSearch.tsx (Apache-2.0).
import { Trans, useLingui } from "@lingui/react/macro";
import { ArrowUpRight, Search as SearchIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type Payload, type Thread } from "../lib/api";
import { userError } from "../lib/user_error";

type SearchKind = "agents" | "messages" | "memory";
const kinds: SearchKind[] = ["agents", "messages", "memory"];
function rowsFor(result: Payload, kind: SearchKind): Payload[] {
  const rows = result[kind];
  return Array.isArray(rows)
    ? rows.filter(
        (row): row is Payload => row !== null && typeof row === "object" && !Array.isArray(row),
      )
    : [];
}
function KindLabel({ kind }: { kind: SearchKind }) {
  return kind === "agents" ? (
    <Trans>Agents</Trans>
  ) : kind === "messages" ? (
    <Trans>Messages</Trans>
  ) : (
    <Trans>Memory</Trans>
  );
}
function resultHref(kind: SearchKind, row: Payload, threads: Thread[]) {
  if (kind === "agents" && typeof row.id === "string") return `/app/${encodeURIComponent(row.id)}`;
  if (kind === "memory" && typeof row.agent_id === "string")
    return `/app/${encodeURIComponent(row.agent_id)}`;
  if (typeof row.thread_id !== "string") return null;
  const thread = threads.find((entry) => entry.id === row.thread_id);
  if (thread?.agent_id)
    return `/app/${encodeURIComponent(thread.agent_id)}?thread=${encodeURIComponent(thread.id)}`;
  if (thread?.group_id)
    return `/app/g/${encodeURIComponent(thread.group_id)}?thread=${encodeURIComponent(thread.id)}`;
  return null;
}

export function SpaceSearch() {
  const { t } = useLingui();
  const [params, setParams] = useSearchParams();
  const initialQuery = params.get("q") ?? "";
  const [query, setQuery] = useState(initialQuery);
  const [searched, setSearched] = useState("");
  const [result, setResult] = useState<Payload | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const generation = useRef(0);
  const performSearch = useCallback(async (term: string) => {
    const current = ++generation.current;
    setBusy(true);
    setError(undefined);
    setResult(null);
    setSearched(term);
    const [search, metadata] = await Promise.allSettled([
      api.get<Payload>(`/search?q=${encodeURIComponent(term)}`),
      api.get<Thread[]>("/threads"),
    ]);
    if (current !== generation.current) return;
    if (search.status === "fulfilled") setResult(search.value);
    else setError(search.reason);
    if (metadata.status === "fulfilled") setThreads(metadata.value);
    setBusy(false);
  }, []);
  useEffect(() => {
    const term = initialQuery.trim().slice(0, 200);
    setQuery(term);
    if (term) void performSearch(term);
    else {
      setResult(null);
      setBusy(false);
      setError(undefined);
    }
    return () => {
      generation.current += 1;
    };
  }, [initialQuery, performSearch]);
  const total = result ? kinds.reduce((count, kind) => count + rowsFor(result, kind).length, 0) : 0;

  return (
    <section className="workspace-surface" data-testid="workspace-search">
      <header className="workspace-surface-header">
        <div className="workspace-surface-heading">
          <h1>
            <Trans>Search your workspace</Trans>
          </h1>
          <p>
            <Trans>Find your agents, conversations and memory.</Trans>
          </p>
        </div>
      </header>
      <form
        className="workspace-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          const term = query.trim();
          if (!term) return;
          if (term === initialQuery) void performSearch(term);
          else setParams({ q: term });
        }}
      >
        <label className="workspace-search-field">
          <span className="sr-only">
            <Trans>Search messages, memory and notes</Trans>
          </span>
          <SearchIcon size={18} aria-hidden="true" />
          <input
            type="search"
            value={query}
            required
            maxLength={200}
            placeholder={t`Search your workspace`}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="workspace-button workspace-button-primary"
          disabled={busy || !query.trim()}
        >
          {busy ? <Trans>Searching…</Trans> : <Trans>Search</Trans>}
        </button>
      </form>
      {error != null && (
        <p className="workspace-error" role="alert">
          {userError(error)}
        </p>
      )}
      <div className="workspace-surface-body workspace-search-results" aria-busy={busy}>
        {busy ? (
          <p className="workspace-empty" role="status">
            <Trans>Searching…</Trans>
          </p>
        ) : result && total === 0 ? (
          <div className="workspace-empty">
            <SearchIcon size={28} aria-hidden="true" />
            <p>
              <Trans>No results</Trans>
            </p>
            <bdi>{searched}</bdi>
          </div>
        ) : result ? (
          kinds.map((kind) => {
            const rows = rowsFor(result, kind);
            if (!rows.length) return null;
            return (
              <section className="workspace-search-group" key={kind}>
                <h2>
                  <KindLabel kind={kind} />
                  <span className="workspace-count">{rows.length}</span>
                </h2>
                {rows.map((row, index) => {
                  const href = resultHref(kind, row, threads);
                  const content = (
                    <>
                      <span className="workspace-search-result-heading">
                        <strong dir="auto">
                          {typeof row.name === "string" ? (
                            row.name
                          ) : kind === "messages" ? (
                            <Trans>Message</Trans>
                          ) : (
                            <Trans>Memory</Trans>
                          )}
                        </strong>
                        {href && <ArrowUpRight size={15} aria-hidden="true" />}
                      </span>
                      {typeof row.content === "string" && (
                        <span className="workspace-search-snippet" dir="auto">
                          {row.content}
                        </span>
                      )}
                    </>
                  );
                  return href ? (
                    <Link
                      className="workspace-search-result"
                      key={String(row.id ?? row.agent_id ?? index)}
                      to={href}
                    >
                      {content}
                    </Link>
                  ) : (
                    <article
                      className="workspace-search-result"
                      key={String(row.id ?? row.agent_id ?? index)}
                    >
                      {content}
                    </article>
                  );
                })}
              </section>
            );
          })
        ) : (
          error == null && (
            <div className="workspace-empty">
              <SearchIcon size={28} aria-hidden="true" />
              <p>
                <Trans>Search messages, memory and notes</Trans>
              </p>
            </div>
          )
        )}
      </div>
    </section>
  );
}
