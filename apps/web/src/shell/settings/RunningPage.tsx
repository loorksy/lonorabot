import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { useEffect, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { SkRows } from "../Skeleton";
import { useToast } from "../Toast";
import { ago } from "./OwnerPage";
import { Empty, Note, useLoad } from "./ui";

type Process = {
  pid: number;
  agent_id: string;
  agent_name: string;
  command: string;
  started_at: string | null;
  stopping: boolean;
};
type Running = {
  listed_at: string | null;
  stale: boolean;
  processes: Process[];
  stopping_all: boolean;
};

/** How often the open view asks again: the Gateway lists the workspace every 10 s and
 * carries out a stop within about 2 s. */
const REFRESH_MS = 4000;

/* «ما يعمل الآن» (mandate 7.1.5): every process in the owner's workspace with the agent that
   started it; one tap stops one process, one tap stops all of them. */
export function RunningPage() {
  const data = useShellData();
  const toast = useToast();
  const [tick, setTick] = useState(0);
  const running = useLoad(() => api.get<Running>("/workspace/running"), [tick]);
  // Taps not yet seen in a server answer; each answer says what is being stopped.
  const [asked, setAsked] = useState<Set<string>>(new Set());
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") setTick((value) => value + 1);
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);
  const view = running.value;
  useEffect(() => {
    if (view) setAsked(new Set());
  }, [view]);
  const processes = view?.processes ?? [];
  const key = (item: Process) => `${item.agent_id}:${item.pid}`;
  const stopAll = (view?.stopping_all ?? false) || asked.has("all");
  // An out-of-date list (the workspace has not answered for a minute) takes no stop.
  const stale = view?.stale ?? false;

  const send = async (path: string, body: object, mark: string) => {
    setAsked((current) => new Set(current).add(mark));
    try {
      await api.post(path, body);
      toast(t`Stopping…`, { type: "success" });
      setTick((value) => value + 1);
    } catch (error) {
      setAsked((current) => {
        const next = new Set(current);
        next.delete(mark);
        return next;
      });
      toast(userError(error), { type: "error" });
    }
  };

  const agents = [...new Set(processes.map((item) => item.agent_id))];
  return (
    <>
      <div className="actions">
        <button
          type="button"
          className="btn danger"
          data-testid="stop-all"
          disabled={!processes.length || stopAll || stale}
          onClick={() => void send("/workspace/running/stop-all", {}, "all")}
        >
          <Icon name="stop" />
          {stopAll ? <Trans>Stopping all…</Trans> : <Trans>Stop all</Trans>}
        </button>
      </div>
      {stale && view?.listed_at ? (
        <p className="pad muted small" role="status" data-testid="running-stale">
          <Trans>
            The workspace last answered {ago(view.listed_at)}; this list may be out of date.
          </Trans>
        </p>
      ) : null}
      {!view && running.loading ? (
        <SkRows count={3} />
      ) : running.error && !view ? (
        <p className="pad muted small" role="alert">
          {userError(running.error)}
        </p>
      ) : view && !processes.length ? (
        <Empty>
          <Trans>Nothing is running in the workspace.</Trans>
        </Empty>
      ) : (
        agents.map((agentId) => {
          const agent = data.agents.find((item) => item.id === agentId);
          const own = processes.filter((item) => item.agent_id === agentId);
          const name = own[0]?.agent_name ?? "";
          return (
            <section key={agentId} aria-label={name}>
              <h3 className="running-agent">
                {agent && <AgentAvatar agent={agent} />}
                <bdi>{name}</bdi>
              </h3>
              <ul className="group">
                {own.map((item) => {
                  const stopping = item.stopping || stopAll || asked.has(key(item));
                  return (
                    <li className="row" key={key(item)} data-testid="running-process">
                      <span className="row-icon">
                        <Icon name="cpu" />
                      </span>
                      <span className="body">
                        <strong>
                          <bdi dir="ltr" className="ltr">
                            {item.command || t`(no command line)`}
                          </bdi>
                        </strong>
                        {item.started_at && (
                          <small>
                            <Trans>Started {ago(item.started_at)}</Trans>
                          </small>
                        )}
                      </span>
                      {stopping ? (
                        <span className="badge off" role="status">
                          <Trans>Stopping…</Trans>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="btn sm outline"
                          disabled={stale}
                          aria-label={t`Stop ${item.command}`}
                          onClick={() =>
                            void send(
                              "/workspace/running/stop",
                              { pid: item.pid, agent_id: item.agent_id },
                              key(item),
                            )
                          }
                        >
                          <Trans>Stop</Trans>
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })
      )}
      <Note>
        {view?.listed_at ? (
          <Trans>
            Every process your agents run in the workspace, with the agent that started it. Updated{" "}
            {ago(view.listed_at)}.
          </Trans>
        ) : (
          <Trans>
            Every process your agents run in the workspace, with the agent that started it.
          </Trans>
        )}
      </Note>
    </>
  );
}
