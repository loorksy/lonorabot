import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { readinessTime, watchCondition, watchUntil } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useCallback, useState } from "react";
import { watchSummary } from "../../components/market/MarketWatch";
import type { Agent, Resource } from "../../lib/api";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { useRead } from "../../shell/agent/shared";
import { SkRows } from "../../shell/Skeleton";
import { useSheets } from "../../shell/sheets/SheetHost";
import { useToast } from "../../shell/Toast";

/* The agent's watches (reference wtRows, Desktop-37 8241-8244), on its page and in the
   «المراقبات» sheet: condition · until; pause / resume · «تمديد ساعتين» · cancel (with undo),
   then «مراقبة جديدة» (a condition schedule creates a market watch, Q39). Owner controls
   through POST /api/watches/{id}/control. */
export function WatchList({ agent, onNew }: { agent: Agent; onNew: () => void }) {
  const watches = useRead<Resource[]>(`/watches?agent_id=${encodeURIComponent(agent.id)}`);
  const { refresh } = useClient();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const send = async (id: string, body: Record<string, unknown>) => {
    const row = await api.post<Resource>(`/watches/${encodeURIComponent(id)}/control`, body);
    watches.reload();
    refresh();
    return row;
  };
  const control = async (
    id: string,
    body: Record<string, unknown>,
    done: (row: Resource) => string,
    undo?: () => Promise<unknown>,
  ) => {
    setBusy(id);
    try {
      const row = await send(id, body);
      toast(done(row), {
        type: "success",
        ...(undo && {
          action: {
            label: t`Undo`,
            run: () => void undo().catch((failure) => toast(userError(failure), { type: "error" })),
          },
        }),
      });
    } catch (failure) {
      toast(userError(failure), { type: "error" });
    } finally {
      setBusy(null);
    }
  };
  const list = (watches.value ?? []).filter(
    (row) => row.payload.enabled !== false || row.state?.code === "watch_paused",
  );
  return (
    <>
      {watches.error != null ? (
        <p role="alert">{userError(watches.error)}</p>
      ) : !watches.value ? (
        <SkRows count={1} />
      ) : list.length ? (
        <div className="group">
          {list.map((row) => {
            const w = watchSummary(row);
            const paused = row.state?.code === "watch_paused";
            return (
              <div
                key={w.id}
                className={`row wt-row wt-${paused ? "paused" : "active"}`}
                data-watch={w.id}
              >
                <span className="row-icon">
                  <Icon name={paused ? "pause" : "radar"} />
                </span>
                <span className="body">
                  <strong className="ltr-mix" dir="auto">
                    {watchCondition(w, i18n.locale)}
                  </strong>
                  <small>
                    {watchUntil(w, i18n.locale)}
                    {paused ? ` · ${t`Paused for now`}` : ""}
                  </small>
                  <span className="wt-acts">
                    <button
                      type="button"
                      className="btn sm outline"
                      disabled={busy === w.id}
                      onClick={() =>
                        void control(w.id, { action: paused ? "resume" : "pause" }, () =>
                          paused ? t`Watch resumed` : t`Watch paused`,
                        )
                      }
                    >
                      {paused ? <Trans>Resume</Trans> : <Trans>Pause for now</Trans>}
                    </button>
                    <button
                      type="button"
                      className="btn sm outline"
                      disabled={busy === w.id || !w.expires_at}
                      onClick={() =>
                        void control(w.id, { action: "extend", hours: 2 }, (next) => {
                          const until = readinessTime(String(next.payload.expires_at), i18n.locale);
                          return t`Extended until ${until}`;
                        })
                      }
                    >
                      <Trans>Extend two hours</Trans>
                    </button>
                    <button
                      type="button"
                      className="btn sm danger"
                      disabled={busy === w.id}
                      onClick={() =>
                        void control(
                          w.id,
                          { action: "cancel" },
                          () => t`Watch cancelled`,
                          () => send(w.id, { action: "resume" }),
                        )
                      }
                    >
                      <Trans>Cancel</Trans>
                    </button>
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="pad muted small">
          <Trans>No watches.</Trans>
        </p>
      )}
      <button type="button" className="btn full outline" onClick={onNew}>
        <Trans>New watch</Trans>
      </button>
    </>
  );
}

/** «مراقبة جديدة»: the schedule form for this agent, on «عند تحقق شرط». */
export const newWatchPath = (agent: Agent) =>
  `/app/new-schedule?agent=${encodeURIComponent(agent.id)}&kind=condition`;

/** `go` comes from the caller: a sheet body renders outside the navigation provider. */
export function useWatchesSheet(go: (path: string) => void) {
  const sheets = useSheets();
  return useCallback(
    (agent: Agent) => {
      const title = t`Watches · ${agent.name}`;
      sheets.open({
        id: "watches",
        title,
        label: title,
        body: (
          <>
            <WatchList
              agent={agent}
              onNew={() => {
                sheets.close();
                go(newWatchPath(agent));
              }}
            />
            <p className="note">
              <Trans>
                A watch ends on its own at its time; you can pause, extend or cancel it.
              </Trans>
            </p>
          </>
        ),
      });
    },
    [sheets, go],
  );
}
