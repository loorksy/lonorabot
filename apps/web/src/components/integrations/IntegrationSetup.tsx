import { Trans } from "@lingui/react/macro";
import type { Agent } from "@lonora/contracts";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Resource } from "../../lib/api";
import { resources } from "../../lib/rpc";
import { userError } from "../../lib/user_error";

/** Channels deliver incoming messages to one agent's conversation, picked by name. */
const CHANNELS = new Set(["telegram", "webhook"]);

export function IntegrationSetup() {
  const service = useMemo(() => resources("/integrations"), []);
  const [rows, setRows] = useState<Resource[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [type, setType] = useState("brave_search");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [deliverTo, setDeliverTo] = useState("");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState<unknown>();
  const load = useCallback(async () => {
    setRows(await service.list());
    setAgents(await api.get<Agent[]>("/agents"));
  }, [service]);
  useEffect(() => {
    void load().catch(setError);
  }, [load]);
  const channel = CHANNELS.has(type);
  const agentName = (row: Resource) => {
    const id = row.payload.deliver_to_agent_id;
    return typeof id === "string" ? agents.find((agent) => agent.id === id)?.name : undefined;
  };
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
              deliver_to_agent_id: channel && deliverTo ? deliverTo : null,
              allowed_destinations: destination
                ? destination
                    .split(",")
                    .map((v) => v.trim())
                    .filter(Boolean)
                : [],
            });
            setSecret("");
            setName("");
            setUrl("");
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
            <option value="news_feed">
              <Trans>News or RSS feed</Trans>
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
        {type !== "brave_search" && (
          <label>
            <Trans>Feed or webhook URL</Trans>
            <input
              type="url"
              dir="ltr"
              required={type === "news_feed"}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
        )}
        {type === "news_feed" && (
          <p className="muted">
            <Trans>
              Every agent reads this feed. Follow X analysts through their feeds, web search or a
              trusted X MCP server; Lonora never uses your X account.
            </Trans>
          </p>
        )}
        {type !== "news_feed" && (
          <label>
            <Trans>Secret or API token</Trans>
            <input
              type="password"
              autoComplete="off"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
            />
          </label>
        )}
        {channel && (
          <>
            <label>
              <Trans>Deliver incoming messages to</Trans>
              <select
                value={deliverTo}
                required
                data-deliver-to
                onChange={(e) => setDeliverTo(e.target.value)}
              >
                <option value="" disabled>
                  <Trans>Choose an agent</Trans>
                </option>
                {agents
                  .filter((agent) => agent.role !== "delegated")
                  .map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              <Trans>Allowed destinations · comma separated</Trans>
              <input
                dir="ltr"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
              />
            </label>
          </>
        )}
        <button type="submit" className="primary">
          <Trans>Add integration</Trans>
        </button>
      </form>
      {error != null && <p role="alert">{userError(error)}</p>}
      {rows.map((row) => (
        <div className="card row" key={row.id}>
          <span dir="auto">
            {String(row.payload.name)}
            {agentName(row) ? ` · ${agentName(row)}` : ""}
          </span>
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
