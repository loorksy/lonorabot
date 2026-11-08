import { i18n } from "@lingui/core";
import type { DeviceChallenge, OwnerAction, OwnerActionDecision } from "@lonora/contracts";
import {
  mergeOwnerAction,
  type OwnerActionButton,
  ownerActionCard,
  ownerActionChoices,
  ownerActionText,
  webDeviceProof,
  webDeviceSupported,
} from "@lonora/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import "./owner-action-card.css";

/** The conversation's owner action cards; refreshed by every runtime revision. */
export function useOwnerActions(threadId: string) {
  const { revision } = useClient();
  const [rows, setRows] = useState<OwnerAction[]>([]);
  const [error, setError] = useState<unknown>();
  const current = useRef(threadId);
  current.current = threadId;
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<OwnerAction[]>(`/owner-actions?thread_id=${encodeURIComponent(threadId)}`)
      .then((items) => {
        if (!live) return;
        setRows((old) =>
          items.map((item) => {
            const previous = old.find((row) => row.id === item.id);
            return previous ? mergeOwnerAction(previous, item) : item;
          }),
        );
        setError(undefined);
      })
      .catch((cause: unknown) => {
        if (live && !isRequestCancelled(cause)) setError(cause);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision]);
  const update = useCallback((row: OwnerAction) => {
    if (row.thread_id !== current.current) return;
    setRows((old) => old.map((item) => (item.id === row.id ? mergeOwnerAction(item, row) : item)));
  }, []);
  return { rows: rows.filter((row) => row.thread_id === threadId), error, update };
}

/**
 * One owner action card: server facts in the owner's language and one tap. A grant
 * card, or one that raises or removes a money limit, asks for the passkey (registering
 * this device inline the first time); a grant card's switches go with that tap. Every
 * tap goes to the owner-session route, which re-validates.
 */
export function OwnerActionCard({
  row,
  onChanged,
}: {
  row: OwnerAction;
  onChanged: (row: OwnerAction) => void;
}) {
  const locale = i18n.locale;
  const text = ownerActionText(locale);
  const spec = ownerActionCard(row, locale);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const [enroll, setEnroll] = useState(false);
  const [password, setPassword] = useState("");
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const supported = webDeviceSupported();
  async function decide(button: OwnerActionButton) {
    setBusy(true);
    setError(undefined);
    try {
      const choices = ownerActionChoices(row, chosen);
      const body: OwnerActionDecision = {
        decision: button.decision,
        ...(button.decision === "confirm" ? choices.decision : {}),
      };
      if (button.outcome) {
        body.outcome = button.outcome;
        if (note.trim()) body.note = note.trim();
        if (reference.trim()) body.broker_reference = reference.trim();
      }
      if (button.decision === "confirm" && spec.passkey) {
        const challenge = await api.post<DeviceChallenge>(
          `/owner-actions/${row.id}/challenge`,
          choices.challenge,
        );
        body.proof = await webDeviceProof(challenge);
      }
      const updated = await api.post<OwnerAction>(`/owner-actions/${row.id}/decision`, body);
      if (mounted.current) onChanged(updated);
    } catch (cause) {
      if (!mounted.current) return;
      if (cause instanceof ApiError && cause.code === "device_registration_required")
        setEnroll(true);
      setError(cause);
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function register() {
    setBusy(true);
    setError(undefined);
    try {
      const secret = password;
      setPassword("");
      const challenge = await api.post<DeviceChallenge>("/auth/devices/enrollment", {
        password: secret,
        name: text.deviceName,
      });
      await api.post("/auth/devices/enrollment/verify", await webDeviceProof(challenge, true));
      if (mounted.current) setEnroll(false);
    } catch (cause) {
      if (mounted.current) setError(cause);
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <article
      className="card lonora-owner-action"
      data-owner-action={row.id}
      data-owner-action-kind={row.kind}
      data-owner-action-status={row.status}
      aria-label={spec.title}
    >
      <strong dir="auto">{spec.title}</strong>
      {spec.lines.map((line) => (
        <p key={line} dir="auto">
          {line}
        </p>
      ))}
      {spec.hint && (
        <p className="muted" dir="auto">
          {spec.hint}
        </p>
      )}
      {spec.options.length > 0 && (
        <div className="lonora-owner-action-options">
          {spec.options.map((option) => (
            <label key={option.key} className="check" dir="auto">
              <input
                type="checkbox"
                data-owner-action-option={option.key.split(":")[0]}
                checked={chosen[option.key] ?? option.initial}
                disabled={busy}
                onChange={(event) =>
                  setChosen((old) => ({ ...old, [option.key]: event.target.checked }))
                }
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
      )}
      {spec.notes && (
        <div className="lonora-owner-action-notes">
          <label>
            {text.note}
            <input
              dir="auto"
              value={note}
              maxLength={2000}
              disabled={busy}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <label>
            {text.brokerReference}
            <input
              dir="auto"
              value={reference}
              maxLength={200}
              disabled={busy}
              onChange={(event) => setReference(event.target.value)}
            />
          </label>
        </div>
      )}
      {spec.passkey && !supported && <p role="status">{text.passkeyUnsupported}</p>}
      {enroll && (
        <div className="lonora-owner-action-notes">
          <label>
            {text.password}
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={!password || busy || !supported}
            onClick={() => void register()}
          >
            {text.registerDevice}
          </button>
        </div>
      )}
      {spec.buttons.length > 0 && (
        <div className="actions">
          {spec.buttons.map((button) => (
            <button
              key={button.key}
              type="button"
              className={button.primary ? "primary" : undefined}
              data-owner-action-button={button.key}
              disabled={busy || (spec.passkey && button.decision === "confirm" && !supported)}
              onClick={() => void decide(button)}
            >
              {button.label}
            </button>
          ))}
        </div>
      )}
      {spec.outcome && (
        <p role="status" dir="auto" data-owner-action-outcome={row.status}>
          {spec.outcome}
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </article>
  );
}
