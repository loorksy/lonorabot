import { useLingui } from "@lingui/react";
import type { Agent, SupervisionView } from "@lonora/contracts";
import { supervisionRows, supervisionText, unsupervisedAgents } from "@lonora/core";
import { useCallback, useEffect, useState } from "react";
import { api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";

/**
 * Who supervises this agent and whom it supervises, each with one-tap Stop. Lonora's
 * profile lists every agent it supervises by default and offers to supervise again an
 * agent whose grant was stopped. A grant never carries money authority.
 */
export function SupervisionSettings({ agent }: { agent: Agent }) {
  const { i18n } = useLingui();
  const text = supervisionText(i18n.locale);
  const personal = agent.role === "personal";
  const [view, setView] = useState<SupervisionView>();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const load = useCallback(async () => {
    const next = await api.get<SupervisionView>(
      `/supervision?agent_id=${encodeURIComponent(agent.id)}`,
    );
    setView(next);
    if (personal) setAgents(await api.get<Agent[]>("/agents"));
  }, [agent.id, personal]);
  useEffect(() => {
    let active = true;
    setView(undefined);
    setError(undefined);
    load().catch((cause: unknown) => {
      if (active && !isRequestCancelled(cause)) setError(cause);
    });
    return () => {
      active = false;
    };
  }, [load]);
  if (agent.role === "delegated") return null;
  const act = async (request: () => Promise<unknown>) => {
    setBusy(true);
    setError(undefined);
    try {
      await request();
      await load();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  };
  const rows = view ? supervisionRows(view, i18n.locale) : undefined;
  const offered = view && personal ? unsupervisedAgents(view, agents) : [];
  const list = (title: string, items: NonNullable<typeof rows>["supervises"]) =>
    items.length > 0 && (
      <div className="supervision-list">
        <h4 dir="auto">{title}</h4>
        <ul>
          {items.map((row) => (
            <li key={row.grantId} data-supervision-grant={row.grantId}>
              <span dir="auto">
                {row.name} · {row.source}
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={() => act(() => api.post(`/supervision/${row.grantId}/revoke`, {}))}
              >
                {text.stop}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  return (
    <details className="tpl-profile-advanced" data-testid="supervision-settings">
      <summary>{personal ? text.personalTitle : text.title}</summary>
      <p className="muted" dir="auto">
        {personal ? text.personalIntro : text.intro}
      </p>
      {rows && (
        <>
          {list(text.supervises, rows.supervises)}
          {list(text.supervisedBy, rows.supervisedBy)}
          {rows.supervises.length + rows.supervisedBy.length === 0 && !personal && (
            <p className="muted" dir="auto">
              {text.none}
            </p>
          )}
        </>
      )}
      {offered.length > 0 && (
        <div className="supervision-list">
          <h4 dir="auto">{text.notSupervised}</h4>
          <ul>
            {offered.map((other) => (
              <li key={other.id}>
                <bdi>{other.name}</bdi>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    act(() =>
                      api.post("/supervision", {
                        supervisor_id: agent.id,
                        supervised_id: other.id,
                      }),
                    )
                  }
                >
                  {text.supervise}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </details>
  );
}
