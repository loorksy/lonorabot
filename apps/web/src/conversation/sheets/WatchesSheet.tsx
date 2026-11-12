import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { watchCondition, watchUntil } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useCallback, useState } from "react";
import { useAgentLiveState } from "../../lib/agent-live-state";
import type { Agent } from "../../lib/api";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { useSheets } from "../../shell/sheets/SheetHost";
import { useToast } from "../../shell/Toast";

/* «المراقبات · {agent}» (reference wtSheet, Desktop-37 8246-8260): condition · until; pause /
   resume · «تمديد ساعتين» · cancel. Owner controls through POST /api/watches/{id}/control. */
function WatchesBody({ agent }: { agent: Agent }) {
  const { state } = useAgentLiveState(agent.id);
  const { refresh } = useClient();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const control = async (id: string, body: Record<string, unknown>, done: string) => {
    setBusy(id);
    try {
      await api.post(`/watches/${encodeURIComponent(id)}/control`, body);
      refresh();
      toast(done, { type: "success" });
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(null);
    }
  };
  const list = state?.watches ?? [];
  return (
    <>
      {list.length ? (
        <div className="group">
          {list.map((w) => {
            const paused = w.lifecycle === "paused";
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
                    {w.expires_at ? watchUntil(w, i18n.locale) : ""}
                    {paused ? ` · ${t`paused`}` : ""}
                  </small>
                  <span className="wt-acts">
                    <button
                      type="button"
                      className="btn sm outline"
                      disabled={busy === w.id}
                      onClick={() =>
                        void control(
                          w.id,
                          { action: paused ? "resume" : "pause" },
                          paused ? t`The watch resumed` : t`The watch is paused`,
                        )
                      }
                    >
                      {paused ? <Trans>Resume</Trans> : <Trans>Pause</Trans>}
                    </button>
                    <button
                      type="button"
                      className="btn sm outline"
                      disabled={busy === w.id || !w.expires_at}
                      onClick={() =>
                        void control(w.id, { action: "extend", hours: 2 }, t`Extended by two hours`)
                      }
                    >
                      <Trans>Extend two hours</Trans>
                    </button>
                    <button
                      type="button"
                      className="btn sm danger"
                      disabled={busy === w.id}
                      onClick={() =>
                        void control(w.id, { action: "cancel" }, t`The watch was cancelled`)
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
      <p className="note">
        <Trans>A watch ends on its own at its time; you can pause, extend or cancel it.</Trans>
      </p>
    </>
  );
}

export function useWatchesSheet() {
  const sheets = useSheets();
  return useCallback(
    (agent: Agent) => {
      const title = t`Watches · ${agent.name}`;
      sheets.open({ id: "watches", title, label: title, body: <WatchesBody agent={agent} /> });
    },
    [sheets],
  );
}
