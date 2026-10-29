import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { Agent, Routine } from "@lonora/contracts";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@lonora/ui-web";
import { useState } from "react";
import { useOverlayHistory } from "../hooks/useOverlayHistory";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
import { RoutineSchedule, type Schedule } from "./RoutineSchedule";
import { AgentPicker } from "./shell/bot-picker";

export function RoutineEditor({
  routine,
  agents,
  onClose,
  onSaved,
}: {
  routine: Routine | null;
  agents: Agent[];
  onClose: () => void;
  onSaved: () => void;
}) {
  useOverlayHistory(true, onClose);
  const [agent, setAgent] = useState(routine?.agent_id ?? agents[0]?.id ?? "");
  const [prompt, setPrompt] = useState(routine?.prompt ?? "");
  const [enabled, setEnabled] = useState(routine?.enabled ?? true);
  const [schedule, setSchedule] = useState<Schedule>({
    mode: routine?.cron ? "cron" : "interval",
    minutes: (routine?.interval_seconds ?? 3600) / 60,
    cron: routine?.cron ?? "0 9 * * 1-5",
    timezone: routine?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {routine ? <Trans>Edit routine</Trans> : <Trans>Create routine</Trans>}
          </DialogTitle>
        </DialogHeader>
        <form
          className="tpl-profile-form"
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            setError(undefined);
            const body = {
              prompt: prompt.trim(),
              interval_seconds: schedule.mode === "interval" ? schedule.minutes * 60 : null,
              cron: schedule.mode === "cron" ? schedule.cron : null,
              timezone: schedule.timezone,
              enabled,
            };
            try {
              if (routine) await api.put(`/routines/${routine.id}`, body);
              else await api.post(`/routines/${agent}`, body);
              onSaved();
              onClose();
            } catch (cause) {
              setError(cause);
            } finally {
              setBusy(false);
            }
          }}
        >
          {!routine && <AgentPicker agents={agents} value={agent} onChange={setAgent} />}
          <label>
            <Trans>Task</Trans>
            <textarea
              aria-label={t`Task`}
              required
              rows={4}
              maxLength={8000}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
            />
          </label>
          <RoutineSchedule value={schedule} onChange={setSchedule} />
          <label className="check">
            <input
              type="checkbox"
              role="switch"
              data-lonora-switch="true"
              aria-checked={enabled}
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <Trans>Enabled</Trans>
          </label>
          {error != null && <p role="alert">{userError(error)}</p>}
          <div className="actions">
            <button type="submit" className="primary" disabled={busy || !agent || !prompt.trim()}>
              <Trans>Save</Trans>
            </button>
            <button type="button" disabled={busy} onClick={onClose}>
              <Trans>Close</Trans>
            </button>
            {routine && (
              <button
                type="button"
                className="danger"
                disabled={busy}
                onClick={() => {
                  setBusy(true);
                  void api
                    .delete(`/routines/${routine.id}`)
                    .then(() => {
                      onSaved();
                      onClose();
                    })
                    .catch(setError)
                    .finally(() => setBusy(false));
                }}
              >
                <Trans>Delete</Trans>
              </button>
            )}
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
