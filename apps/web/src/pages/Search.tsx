import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { api, type Payload } from "../lib/api";
import { userError } from "../lib/user_error";
export function Search() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <section>
      <h1>
        <Trans>Search your workspace</Trans>
      </h1>
      <form
        className="inline-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            setResult(await api.get<Payload>(`/search?q=${encodeURIComponent(query)}`));
            setError(undefined);
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          <Trans>Search messages, memory and notes</Trans>
          <input value={query} onChange={(e) => setQuery(e.target.value)} required />
        </label>
        <button type="submit" className="primary" disabled={busy}>
          <Trans>Search</Trans>
        </button>
      </form>
      {error != null && <p role="alert">{userError(error)}</p>}
      {result &&
        Object.entries(result).map(([kind, rows]) => (
          <section key={kind}>
            <h2>
              {kind === "messages" ? (
                <Trans>Messages</Trans>
              ) : kind === "memory" ? (
                <Trans>Memory</Trans>
              ) : (
                <Trans>Notes and files</Trans>
              )}
            </h2>
            {Array.isArray(rows) &&
              rows.map((row, i) => {
                const entry = row as Payload;
                return (
                  <article className="card" key={String(entry.id ?? i)}>
                    <p dir="auto" className="wrap">
                      {String(entry.content ?? entry.title ?? entry.name ?? JSON.stringify(entry))}
                    </p>
                  </article>
                );
              })}
          </section>
        ))}
    </section>
  );
}
