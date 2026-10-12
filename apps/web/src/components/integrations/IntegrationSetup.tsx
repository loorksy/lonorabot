import { Trans } from "@lingui/react/macro";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Resource } from "../../lib/api";
import { resources } from "../../lib/rpc";
import { userError } from "../../lib/user_error";
export function IntegrationSetup() {
  const service = useMemo(() => resources("/integrations"), []);
  const [rows, setRows] = useState<Resource[]>([]);
  const [type, setType] = useState("brave_search");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [threadId, setThreadId] = useState("");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState<unknown>();
  const load = useCallback(async () => {
    setRows(await service.list());
  }, [service]);
  useEffect(() => {
    void load().catch(setError);
  }, [load]);
  return (
    <section>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            let secret_id: string | null = null;
            if (secret)
              secret_id = (
                await api.post<{ id: string }>("/integrations/secrets", { name, value: secret })
              ).id;
            await service.create({
              name,
              type,
              url: url || null,
              secret_id,
              enabled: true,
              thread_id: threadId || null,
              allowed_destinations: destination
                ? destination
                    .split(",")
                    .map((v) => v.trim())
                    .filter(Boolean)
                : [],
            });
            setSecret("");
            setName("");
            await load();
          } catch (err) {
            setError(err);
          }
        }}
      >
        <h2>
          <Trans>Integrations</Trans>
        </h2>
        <label>
          <Trans>Type</Trans>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="brave_search">
              <Trans>Brave web search</Trans>
            </option>
            <option value="economic_calendar">
              <Trans>Economic calendar feed</Trans>
            </option>
            <option value="telegram">Telegram</option>
            <option value="webhook">
              <Trans>Signed webhook</Trans>
            </option>
          </select>
        </label>
        <label>
          <Trans>Name</Trans>
          <input required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          <Trans>Feed or webhook URL</Trans>
          <input type="url" dir="ltr" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label>
          <Trans>Secret or API token</Trans>
          <input
            type="password"
            autoComplete="off"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </label>
        <label>
          <Trans>Conversation ID for incoming messages</Trans>
          <input dir="ltr" value={threadId} onChange={(e) => setThreadId(e.target.value)} />
        </label>
        <label>
          <Trans>Allowed destinations · comma separated</Trans>
          <input dir="ltr" value={destination} onChange={(e) => setDestination(e.target.value)} />
        </label>
        <button type="submit" className="primary">
          <Trans>Add integration</Trans>
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
    </section>
  );
}
