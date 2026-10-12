import { Trans } from "@lingui/react/macro";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Resource } from "../lib/api";
import { resources } from "../lib/rpc";
import { userError } from "../lib/user_error";
export function McpServersOverlay() {
  const service = useMemo(() => resources("/mcp"), []);
  const [rows, setRows] = useState<Resource[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<unknown>();
  const load = useCallback(async () => {
    setRows(await service.list());
  }, [service]);
  useEffect(() => {
    void load().catch(setError);
  }, [load]);
  return (
    <>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            const secret_id = secret
              ? (await api.post<{ id: string }>("/integrations/secrets", { name, value: secret }))
                  .id
              : null;
            await service.create({
              name,
              url,
              transport: "http",
              command: [],
              secret_id,
              enabled: true,
            });
            setSecret("");
            await load();
          } catch (err) {
            setError(err);
          }
        }}
      >
        <h2>
          <Trans>MCP servers</Trans>
        </h2>
        <p className="muted">
          <Trans>Connect a server to make its tools available to your agents.</Trans>
        </p>
        <label>
          <Trans>Name</Trans>
          <input required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          <Trans>Server URL</Trans>
          <input
            required
            type="url"
            dir="ltr"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <label>
          <Trans>Access token</Trans>
          <input
            type="password"
            autoComplete="off"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </label>
        <button type="submit" className="primary">
          <Trans>Connect server</Trans>
        </button>
      </form>
      {error != null && <p role="alert">{userError(error)}</p>}
      {rows.map((row) => (
        <div className="card row" key={row.id}>
          <span>{String(row.payload.name)}</span>
          <button
            type="button"
            onClick={() =>
              void service
                .update(row, { ...row.payload, enabled: !row.payload.enabled })
                .then(load)
                .catch(setError)
            }
          >
            {row.payload.enabled ? <Trans>Disable</Trans> : <Trans>Enable</Trans>}
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => void service.delete(row.id).then(load).catch(setError)}
          >
            <Trans>Delete</Trans>
          </button>
        </div>
      ))}
    </>
  );
}
