import { Trans, useLingui } from "@lingui/react/macro";
import type { DeviceChallenge, SuperBotRequest } from "@lonora/contracts";
import { webDeviceProof, webDeviceSupported } from "@lonora/core";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

export function SuperBotCards({
  agentId,
  threadId,
  goalId,
}: {
  agentId: string;
  threadId?: string;
  goalId?: string;
}) {
  const { t } = useLingui();
  const { revision, refresh } = useClient();
  const [rows, setRows] = useState<SuperBotRequest[]>([]);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState("");
  const [enroll, setEnroll] = useState(false);
  const [password, setPassword] = useState("");
  const reload = useCallback(
    async () =>
      setRows(await api.get<SuperBotRequest[]>(`/agents/${encodeURIComponent(agentId)}/super-bot`)),
    [agentId],
  );
  useEffect(() => {
    void revision;
    let active = true;
    void api
      .get<SuperBotRequest[]>(`/agents/${encodeURIComponent(agentId)}/super-bot`)
      .then((items) => {
        if (active) {
          setRows(items);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (active) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [agentId, revision]);
  async function act(id: string, action: string) {
    setBusy(id);
    setError(undefined);
    try {
      if (action === "activate") {
        const challenge = await api.post<DeviceChallenge>(`/super-bot/${id}/challenge`, {});
        await api.post("/super-bot/verify", await webDeviceProof(challenge));
      } else await api.post("/super-bot/control", { request_id: id, action });
      await reload();
      refresh();
    } catch (cause) {
      setError(cause);
      await reload().catch(() => undefined);
    } finally {
      setBusy("");
    }
  }
  const modes = { advisory: t`Advisory`, supervised: t`Supervised`, autonomous: t`Autonomous` };
  const statuses = {
    pending: t`Waiting for device authorization`,
    activated: t`Active`,
    expired: t`Expired`,
    rejected: t`Rejected`,
    cancelled: t`Cancelled`,
    paused: t`Paused`,
    disabled: t`Stopped`,
  };
  const visible = rows
    .filter(
      (row) => (!threadId || row.thread_id === threadId) && (!goalId || row.goal_id === goalId),
    )
    .slice(0, 5);
  if (!visible.length && !error) return null;
  return (
    <section aria-label={t`Super Bot`}>
      {error != null && <p role="alert">{userError(error)}</p>}
      {visible.map((row) => (
        <article key={row.id} className="tpl-activity-run" data-super-bot-id={row.id}>
          <strong>
            <Trans>Super Bot</Trans> · {statuses[row.status]}
          </strong>
          <p>
            {modes[row.mode]} · <bdi>{row.envelope.symbol}</bdi>
          </p>
          <p dir="auto">{row.envelope.goal_title}</p>
          <p dir="auto">{row.envelope.objective}</p>
          <details>
            <summary>
              <Trans>Review plan</Trans>
            </summary>
            {row.envelope.steps.map((step) => (
              <p key={step.id} dir="auto">
                {step.title}
                {step.trade && (
                  <>
                    {" "}
                    ·{" "}
                    <bdi>
                      {step.trade.action} {step.trade.symbol} {step.trade.volume} @{" "}
                      {step.trade.price ?? "—"}
                      {" · "}
                      {step.trade.position_id ??
                        step.trade.order_id ??
                        step.trade.target_step_id ??
                        "—"}
                    </bdi>{" "}
                    · <Trans>Stop loss</Trans>: <bdi>{step.trade.stop_loss ?? "—"}</bdi> ·{" "}
                    <Trans>Take profit</Trans>: <bdi>{step.trade.take_profit ?? "—"}</bdi>
                  </>
                )}
              </p>
            ))}
          </details>
          <p>
            <Trans>Maximum volume</Trans>: <bdi>{row.envelope.maximum_volume ?? "—"}</bdi> ·{" "}
            <Trans>Maximum trade actions</Trans>: {row.envelope.max_trade_actions}
          </p>
          <p>
            {row.envelope.allow_manual_positions ? (
              <Trans>Manual position management allowed</Trans>
            ) : (
              <Trans>Manual position management excluded</Trans>
            )}
          </p>
          {row.status === "pending" ? (
            <div className="row">
              <button
                type="button"
                disabled={Boolean(busy) || !webDeviceSupported()}
                onClick={() => void act(row.id, "activate")}
              >
                <Trans>Activate with device authentication</Trans>
              </button>
              <button type="button" disabled={Boolean(busy)} onClick={() => setEnroll(!enroll)}>
                <Trans>Register a passkey</Trans>
              </button>
              <button
                type="button"
                disabled={Boolean(busy)}
                onClick={() => void act(row.id, "reject")}
              >
                <Trans>Reject</Trans>
              </button>
            </div>
          ) : (
            ["activated", "paused"].includes(row.status) && (
              <button
                type="button"
                disabled={Boolean(busy)}
                onClick={() => void act(row.id, "stop")}
              >
                <Trans>Stop Super Bot</Trans>
              </button>
            )
          )}
        </article>
      ))}
      {enroll && (
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy("enroll");
            setError(undefined);
            const current = password;
            setPassword("");
            try {
              const challenge = await api.post<DeviceChallenge>("/auth/devices/enrollment", {
                password: current,
                name: t`My device`,
              });
              await api.post(
                "/auth/devices/enrollment/verify",
                await webDeviceProof(challenge, true),
              );
              setEnroll(false);
              refresh();
            } catch (cause) {
              setError(cause);
            } finally {
              setBusy("");
            }
          }}
        >
          <label>
            <Trans>Confirm account password</Trans>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button type="submit" disabled={Boolean(busy) || !webDeviceSupported()}>
            <Trans>Register this device</Trans>
          </button>
          <button
            type="button"
            onClick={() => {
              setEnroll(false);
              setPassword("");
            }}
          >
            <Trans>Cancel</Trans>
          </button>
        </form>
      )}
      {!webDeviceSupported() && (
        <p>
          <Trans>Secure device authentication is unavailable in this browser.</Trans>
        </p>
      )}
    </section>
  );
}
