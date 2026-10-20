import { Trans, useLingui } from "@lingui/react/macro";
import type { DeviceChallenge, SuperBotRequest } from "@lonora/contracts";
import { mergeSuperBotRequest, webDeviceProof, webDeviceSupported } from "@lonora/core";
import { Check, ChevronRight, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ApiError, api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import "./super-bot-card.css";

export function useSuperBotRequests(
  agentId: string,
  { threadId, goalId }: { threadId?: string; goalId?: string } = {},
) {
  const { revision, refresh } = useClient();
  const [rows, setRows] = useState<SuperBotRequest[]>([]);
  const [error, setError] = useState<unknown>();
  const scope = useRef(agentId);
  scope.current = agentId;
  const reload = useCallback(async () => {
    if (!agentId) return;
    const items = await api.get<SuperBotRequest[]>(
      `/agents/${encodeURIComponent(agentId)}/super-bot`,
    );
    if (scope.current === agentId) {
      setRows((current) =>
        items.map((item) => {
          const previous = current.find((value) => value.id === item.id);
          return previous ? mergeSuperBotRequest(previous, item) : item;
        }),
      );
      setError(undefined);
    }
  }, [agentId]);
  useEffect(() => {
    void revision;
    let active = true;
    if (!agentId) {
      setRows([]);
      return;
    }
    void api
      .get<SuperBotRequest[]>(`/agents/${encodeURIComponent(agentId)}/super-bot`)
      .then((items) => {
        if (active) {
          setRows((current) =>
            items.map((item) => {
              const previous = current.find((value) => value.id === item.id);
              return previous ? mergeSuperBotRequest(previous, item) : item;
            }),
          );
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (active && !isRequestCancelled(cause)) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [agentId, revision]);
  const update = useCallback(
    (row: SuperBotRequest) => {
      if (row.agent_id !== scope.current) return;
      setRows((current) =>
        current.map((item) => (item.id === row.id ? mergeSuperBotRequest(item, row) : item)),
      );
      refresh();
    },
    [refresh],
  );
  return {
    rows: rows.filter(
      (row) =>
        row.agent_id === agentId &&
        (!threadId || row.thread_id === threadId) &&
        (!goalId || row.goal_id === goalId),
    ),
    error,
    reload,
    update,
  };
}

/** One durable authorization request, with the full signed scope available on demand. */
export function SuperBotCard({
  row,
  onChanged,
}: {
  row: SuperBotRequest;
  onChanged?: (row: SuperBotRequest) => void;
}) {
  const { t } = useLingui();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [enroll, setEnroll] = useState(false);
  const [password, setPassword] = useState("");
  const [expanded, setExpanded] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const mounted = useRef(true);
  const headingId = useId();
  const supported = webDeviceSupported();
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (expanded) dialog.current?.showModal();
    else dialog.current?.close();
  }, [expanded]);
  const close = () => {
    dialog.current?.close();
    setExpanded(false);
    setEnroll(false);
    setPassword("");
    trigger.current?.focus();
  };
  async function act(action: "activate" | "reject" | "stop") {
    setBusy(true);
    setError(undefined);
    try {
      let updated: SuperBotRequest;
      if (action === "activate") {
        const challenge = await api.post<DeviceChallenge>(`/super-bot/${row.id}/challenge`, {});
        updated = await api.post<SuperBotRequest>(
          "/super-bot/verify",
          await webDeviceProof(challenge),
        );
      } else {
        updated = await api.post<SuperBotRequest>("/super-bot/control", {
          request_id: row.id,
          action,
        });
      }
      if (mounted.current) {
        onChanged?.(updated);
        close();
      }
    } catch (cause) {
      if (!mounted.current || isRequestCancelled(cause)) return;
      setError(cause);
      if (cause instanceof ApiError && cause.code === "device_registration_required") {
        setEnroll(true);
        setExpanded(true);
      }
    } finally {
      if (mounted.current) setBusy(false);
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
  const pending = row.status === "pending";
  const actions = (
    <div className="super-bot-card-actions">
      {pending ? (
        <>
          <button
            type="button"
            className="super-bot-card-allow"
            disabled={busy || !supported}
            aria-label={t`Activate with device authentication`}
            onClick={() => void act("activate")}
          >
            <Trans>Allow</Trans>
          </button>
          <button type="button" disabled={busy} onClick={() => void act("reject")}>
            <Trans>Reject</Trans>
          </button>
        </>
      ) : (
        ["activated", "paused"].includes(row.status) && (
          <button type="button" disabled={busy} onClick={() => void act("stop")}>
            <Trans>Stop Super Bot</Trans>
          </button>
        )
      )}
    </div>
  );
  return (
    <article
      className="super-bot-card"
      data-super-bot-id={row.id}
      data-status={row.status}
      aria-busy={busy}
    >
      <button
        type="button"
        className="super-bot-card-heading"
        ref={trigger}
        aria-label={t`Review plan`}
        aria-haspopup="dialog"
        aria-expanded={expanded}
        onClick={() => setExpanded(true)}
      >
        <span>
          <strong role="status" aria-live="polite">
            {pending ? (
              <Trans>Activate Super Bot?</Trans>
            ) : (
              <>
                <Trans>Super Bot</Trans> · {statuses[row.status]}
              </>
            )}
          </strong>
          <span className="super-bot-card-summary">
            {modes[row.mode]} · <bdi>{row.envelope.symbol}</bdi>
          </span>
        </span>
        {row.status === "activated" ? (
          <Check aria-hidden="true" size={19} />
        ) : (
          <ChevronRight aria-hidden="true" size={19} />
        )}
      </button>
      {!expanded && row.mode === "autonomous" && (
        <p className="super-bot-card-note" data-super-bot-limits>
          <Trans>Maximum volume</Trans>: <bdi>{row.envelope.maximum_volume ?? "—"}</bdi> ·{" "}
          <Trans>Maximum trade actions</Trans>: {row.envelope.max_trade_actions}
        </p>
      )}
      {!expanded && row.envelope.allow_manual_positions && (
        <p className="super-bot-card-note" data-super-bot-manual>
          <Trans>Manual position management allowed</Trans>
        </p>
      )}
      {!expanded && row.envelope.execution_mode === "shadow" && (
        <p className="super-bot-card-note">
          <Trans>Shadow trading — virtual orders only</Trans>
        </p>
      )}
      {pending && (
        <p className="super-bot-card-note">
          <Trans>Your approval is needed.</Trans>
        </p>
      )}
      {error != null && !expanded && (
        <p className="super-bot-card-error" role="alert">
          {userError(error)}
        </p>
      )}
      {!expanded && actions}
      {!supported && pending && (
        <p className="super-bot-card-note">
          <Trans>Secure device authentication is unavailable in this browser.</Trans>
        </p>
      )}
      {expanded && (
        <dialog
          ref={dialog}
          className="super-bot-details"
          aria-labelledby={headingId}
          onCancel={(event) => {
            event.preventDefault();
            close();
          }}
          onClick={(event) => {
            if (event.target === event.currentTarget) close();
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") close();
          }}
          onClose={close}
        >
          <div className="super-bot-details-content">
            <header>
              <h2 id={headingId}>
                <Trans>Super Bot details</Trans>
              </h2>
              <button
                type="button"
                className="super-bot-details-close"
                aria-label={t`Close`}
                onClick={close}
              >
                <X size={20} />
              </button>
            </header>
            <dl>
              <div>
                <dt>
                  <Trans>Market</Trans>
                </dt>
                <dd>
                  <bdi>{row.envelope.symbol}</bdi>
                </dd>
              </div>
              <div>
                <dt>
                  <Trans>Mode</Trans>
                </dt>
                <dd>{modes[row.mode]}</dd>
              </div>
              <div>
                <dt>
                  <Trans>Maximum volume</Trans>
                </dt>
                <dd>
                  <bdi>{row.envelope.maximum_volume ?? "—"}</bdi>
                </dd>
              </div>
              <div>
                <dt>
                  <Trans>Maximum trade actions</Trans>
                </dt>
                <dd>{row.envelope.max_trade_actions}</dd>
              </div>
            </dl>
            <section className="super-bot-plan">
              <h3 dir="auto">{row.envelope.goal_title}</h3>
              <p dir="auto">{row.envelope.objective}</p>
              <ol>
                {row.envelope.steps.map((step) => (
                  <li key={step.id}>
                    <span dir="auto">{step.title}</span>
                    {step.trade && (
                      <p className="super-bot-card-note">
                        <bdi>
                          {step.trade.action} {step.trade.symbol} {step.trade.volume ?? "—"} @{" "}
                          {step.trade.price ?? "—"}
                        </bdi>
                        <br />
                        <Trans>Stop loss</Trans>: <bdi>{step.trade.stop_loss ?? "—"}</bdi> ·{" "}
                        <Trans>Take profit</Trans>: <bdi>{step.trade.take_profit ?? "—"}</bdi>
                        {(step.trade.position_id ??
                          step.trade.order_id ??
                          step.trade.target_step_id) && (
                          <>
                            <br />
                            <bdi>
                              {step.trade.position_id ??
                                step.trade.order_id ??
                                step.trade.target_step_id}
                            </bdi>
                          </>
                        )}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </section>
            <p className="super-bot-card-note">
              {row.envelope.allow_manual_positions ? (
                <Trans>Manual position management allowed</Trans>
              ) : (
                <Trans>Manual position management excluded</Trans>
              )}
            </p>
            {row.envelope.execution_mode === "shadow" && (
              <p className="super-bot-card-note">
                <Trans>Shadow trading — virtual orders only</Trans>
              </p>
            )}
            {error != null && (
              <p className="super-bot-card-error" role="alert">
                {userError(error)}
              </p>
            )}
            {enroll && pending ? (
              <form
                className="super-bot-enrollment"
                onSubmit={async (event) => {
                  event.preventDefault();
                  setBusy(true);
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
                    if (mounted.current) setEnroll(false);
                  } catch (cause) {
                    if (mounted.current && !isRequestCancelled(cause)) setError(cause);
                  } finally {
                    if (mounted.current) setBusy(false);
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
                <div className="super-bot-card-actions">
                  <button
                    type="submit"
                    className="super-bot-card-allow"
                    disabled={busy || !supported || !password}
                  >
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
                </div>
              </form>
            ) : (
              <>
                {actions}
                {pending && supported && (
                  <button
                    type="button"
                    className="super-bot-register"
                    disabled={busy}
                    onClick={() => setEnroll(true)}
                  >
                    <Trans>Register a passkey</Trans>
                  </button>
                )}
              </>
            )}
            {!supported && pending && (
              <p className="super-bot-card-note">
                <Trans>Secure device authentication is unavailable in this browser.</Trans>
              </p>
            )}
          </div>
        </dialog>
      )}
    </article>
  );
}

export function SuperBotCards(props: { agentId: string; threadId?: string; goalId?: string }) {
  const { t } = useLingui();
  const { rows, error, update } = useSuperBotRequests(props.agentId, props);
  if (!rows.length && !error) return null;
  return (
    <section className="super-bot-cards" aria-label={t`Super Bot`}>
      {error != null && <p role="alert">{userError(error)}</p>}
      {rows.slice(0, 5).map((row) => (
        <SuperBotCard key={row.id} row={row} onChanged={update} />
      ))}
    </section>
  );
}
