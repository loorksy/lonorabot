import { i18n } from "@lingui/core";
import type { DeviceChallenge, OwnerAction, OwnerActionDecision } from "@lonora/contracts";
import {
  type CredentialForm,
  mergeOwnerAction,
  type OwnerActionButton,
  type OwnerActionOption,
  ownerActionCard,
  ownerActionChoices,
  ownerActionChoose,
  ownerActionText,
  submitCredential,
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
  // The choice being stored: shown selected until the server's card says so.
  const [choosing, setChoosing] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const supported = webDeviceSupported();
  // The tap that found no passkey on this device: registering continues straight into it.
  const waiting = useRef<OwnerActionButton | null>(null);
  async function decide(button: OwnerActionButton) {
    setBusy(true);
    setError(undefined);
    try {
      waiting.current = button;
      await submit(button);
    } catch (cause) {
      if (!mounted.current) return;
      if (cause instanceof ApiError && cause.code === "device_registration_required")
        setEnroll(true);
      setError(cause);
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function submit(button: OwnerActionButton) {
    const choices = ownerActionChoices(row, chosen);
    const body: OwnerActionDecision = {
      decision: button.decision,
      ...(button.decision === "confirm" ? choices.decision : {}),
    };
    if (button.tier) body.tier = button.tier;
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
    waiting.current = null;
    if (mounted.current) onChanged(updated);
  }
  /** A grant card's Custom or Full delegation: the server stores the choice in the
   * card's draft and answers with the card as it now reads; nothing is signed. */
  async function choose(option: OwnerActionOption) {
    const body = ownerActionChoose(option);
    if (!body || option.initial) return;
    setBusy(true);
    setChoosing(option.key);
    setError(undefined);
    try {
      const updated = await api.post<OwnerAction>(`/owner-actions/${row.id}/decision`, body);
      if (mounted.current) onChanged(updated);
    } catch (cause) {
      if (mounted.current) setError(cause);
    } finally {
      if (mounted.current) {
        setChoosing(null);
        setBusy(false);
      }
    }
  }
  async function connect(form: CredentialForm, values: Record<string, string>) {
    setBusy(true);
    setError(undefined);
    try {
      // The value goes straight to the owner API; the card only learns what was created.
      const connected = await submitCredential(
        (path, body) => api.post<{ id: string }>(path, body),
        form.target,
        values,
      );
      const updated = await api.post<OwnerAction>(`/owner-actions/${row.id}/decision`, {
        decision: "confirm",
        connected,
      } satisfies OwnerActionDecision);
      if (mounted.current) onChanged(updated);
    } catch (cause) {
      if (mounted.current) setError(cause);
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
      // One owner action: the registered device now signs the decision that needed it.
      const button = waiting.current;
      if (button && mounted.current) await submit(button);
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
          {spec.options.map((option) =>
            option.choice ? (
              <div key={option.key} className="lonora-owner-action-choice">
                <label className="check" dir="auto">
                  <input
                    type="radio"
                    name={`owner-action-${row.id}-${option.choice.group}`}
                    data-owner-action-choice={option.choice.value}
                    checked={choosing ? choosing === option.key : option.initial}
                    disabled={busy}
                    onChange={() => void choose(option)}
                  />
                  <span>{option.label}</span>
                </label>
                {option.detail && (
                  <p className="muted" dir="auto" data-owner-action-choice-detail>
                    {option.detail}
                  </p>
                )}
              </div>
            ) : (
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
            ),
          )}
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
      {spec.credential && (
        <CredentialFields
          form={spec.credential}
          busy={busy}
          onSubmit={(values) => void connect(spec.credential as CredentialForm, values)}
        />
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

/** A credential card's secure form: values stay in this component until they are posted
 * to the owner API, and are cleared as soon as they are sent. */
function CredentialFields({
  form,
  busy,
  onSubmit,
}: {
  form: CredentialForm;
  busy: boolean;
  onSubmit: (values: Record<string, string>) => void;
}) {
  const initial = () => Object.fromEntries(form.fields.map((field) => [field.key, field.initial]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  return (
    <form
      className="lonora-owner-action-notes"
      data-owner-action-form={form.target}
      onSubmit={(event) => {
        event.preventDefault();
        const sent = values;
        setValues(initial());
        onSubmit(sent);
      }}
    >
      {form.fields.map((field) => (
        <label key={field.key}>
          {field.label}
          <input
            name={field.key}
            type={field.type}
            dir={field.ltr ? "ltr" : "auto"}
            required={field.required}
            autoComplete={field.type === "password" ? "off" : undefined}
            value={values[field.key] ?? ""}
            disabled={busy}
            onChange={(event) => setValues((old) => ({ ...old, [field.key]: event.target.value }))}
          />
        </label>
      ))}
      <button type="submit" className="primary" disabled={busy} data-owner-action-button="connect">
        {form.submit}
      </button>
    </form>
  );
}
