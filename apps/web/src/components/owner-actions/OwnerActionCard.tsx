import { i18n } from "@lingui/core";
import type { DeviceChallenge, OwnerAction, OwnerActionDecision } from "@lonora/contracts";
import {
  type CredentialForm,
  mergeOwnerAction,
  noticeUndone,
  OWNER_ACTION_CHANGED,
  type OwnerActionButton,
  type OwnerActionOption,
  ownerActionCard,
  ownerActionChoices,
  ownerActionChoose,
  ownerActionLive,
  ownerActionText,
  rereadOwnerAction,
  submitCredential,
  webDeviceProof,
  webDeviceSupported,
} from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

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
  inSheet = false,
  onRenew,
  onLatest,
}: {
  row: OwnerAction;
  onChanged: (row: OwnerAction) => void;
  /** Q12: the same card opened as a sheet from the permission chip or the agent page. */
  inSheet?: boolean;
  /** «طلب جديد» on an expired resolve card (POST /owner-actions/{id}/renew). */
  onRenew?: (row: OwnerAction) => void;
  /** «عرض الأحدث» on a superseded card. */
  onLatest?: (id: string) => void;
}) {
  const locale = i18n.locale;
  const text = ownerActionText(locale);
  const spec = ownerActionCard(row, locale);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const [more, setMore] = useState(false);
  // Q11: «غير معروف» can also stop new trades for the rest of the day (an owner restriction).
  const [pauseToday, setPauseToday] = useState(false);
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
      if (cause instanceof ApiError && cause.code === OWNER_ACTION_CHANGED) await reread();
      setError(cause);
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  /** The card changed on another screen: show it as it is now before another tap. */
  async function reread() {
    try {
      const current = await rereadOwnerAction((path) => api.get<OwnerAction[]>(path), row);
      if (current && mounted.current) onChanged(current);
    } catch {
      // The next runtime revision reads the conversation's cards again.
    }
  }
  async function submit(button: OwnerActionButton) {
    const choices = ownerActionChoices(row, chosen);
    const body: OwnerActionDecision = {
      decision: button.decision,
      ...(button.decision === "confirm" ? choices.decision : {}),
    };
    if (button.tier) body.tier = button.tier;
    if (button.trading_mode) body.trading_mode = button.trading_mode;
    if (button.outcome) {
      body.outcome = button.outcome;
      if (note.trim()) body.note = note.trim();
      if (reference.trim()) body.broker_reference = reference.trim();
      if (button.outcome === "unknown" && pauseToday) body.pause_new_today = true;
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
  const settled = !ownerActionLive(row);
  const notice = NOTICE_KINDS.has(row.kind);
  const kind = ownerActionKindName(row);
  if (notice)
    return (
      <NoticeLine
        row={row}
        text={[spec.title, ...spec.lines].join(" · ")}
        undo={settled ? undefined : spec.buttons.find((button) => button.decision === "confirm")}
        outcome={spec.outcome}
        busy={busy}
        error={error}
        onUndo={(button) => void decide(button)}
      />
    );
  if (settled && !inSheet)
    return (
      <DecisionLine
        row={row}
        kind={kind}
        // A signed grant names Full delegation (the core spec's line for the signed terms).
        choice={spec.lines.find((line) => line === text.delegationFull)}
        text={spec.outcome ?? spec.title}
        onRenew={onRenew}
        onLatest={onLatest}
      />
    );
  const resolve = row.kind === "resolve_operation";
  const left = Date.parse(row.expires_at) - Date.now();
  return (
    // biome-ignore lint/a11y/useSemanticElements: the reference's card is a named group
    <div
      className={`oa st-${row.status} act-${row.kind}${inSheet ? " in-sheet" : ""}`}
      data-oa-mid={row.id}
      data-owner-action={row.id}
      data-owner-action-kind={row.kind}
      data-owner-action-status={row.status}
      aria-label={spec.title}
      role="group"
    >
      <div className="oa-head">
        <span className="oa-ic">
          <Icon name={KIND_ICON[row.kind] ?? "shield"} />
        </span>
        <span className="oa-kind">{spec.title}</span>
        {resolve && left > 0 && left < 3_600_000 && <Countdown until={row.expires_at} />}
      </div>
      {spec.lines.length > 0 && (
        <strong className="oa-title" dir="auto">
          {spec.lines[0]}
        </strong>
      )}
      {spec.lines.slice(1).map((line) => (
        <p key={line} className="oa-sub" dir="auto">
          {line}
        </p>
      ))}
      {spec.hint && (
        <p className="oa-hint" dir="auto">
          <Icon name={spec.passkey ? "fingerprint" : "info"} />
          <span>{spec.hint}</span>
        </p>
      )}
      {spec.options.some((option) => option.choice) && (
        <div className="oa-radios" role="radiogroup">
          {spec.options
            .filter((option) => option.choice)
            .map((option) => {
              const on = choosing ? choosing === option.key : option.initial;
              return (
                // biome-ignore lint/a11y/useSemanticElements: the reference's radio rows
                <button
                  key={option.key}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  className={`oa-radio${on ? " on" : ""}`}
                  aria-label={option.label}
                  data-owner-action-choice={option.choice?.value}
                  disabled={busy}
                  onClick={() => void choose(option)}
                >
                  <span>
                    <strong>{option.label}</strong>
                    {option.detail && on && (
                      <small data-owner-action-choice-detail>{option.detail}</small>
                    )}
                  </span>
                  {on && <Icon name="check" />}
                </button>
              );
            })}
        </div>
      )}
      {spec.options.some((option) => !option.choice) && (
        <div className="oa-fields">
          {spec.options
            .filter((option) => !option.choice)
            .map((option) => {
              const on = chosen[option.key] ?? option.initial;
              return (
                <div key={option.key} className="oa-f">
                  <span className="oa-l" dir="auto">
                    {option.label}
                  </span>
                  <button
                    type="button"
                    className="switch"
                    role="switch"
                    aria-checked={on}
                    aria-label={option.label}
                    data-owner-action-option={option.key.split(":")[0]}
                    disabled={busy}
                    onClick={() => setChosen((old) => ({ ...old, [option.key]: !on }))}
                  />
                </div>
              );
            })}
        </div>
      )}
      {resolve && !settled && (
        <div className="oa-fields">
          <div className="oa-f">
            <span className="oa-l">
              {text.pauseNewToday}
              <small>{text.pauseNewTodayHint}</small>
            </span>
            <button
              type="button"
              className="switch"
              role="switch"
              aria-checked={pauseToday}
              aria-label={text.pauseNewToday}
              data-owner-action-option="pause_new_today"
              disabled={busy}
              onClick={() => setPauseToday((on) => !on)}
            />
          </div>
        </div>
      )}
      {spec.notes &&
        (more ? (
          <div className="oa-fields">
            <label className="oa-input">
              <span>
                {text.noteShort} <small>{text.optional}</small>
              </span>
              <input
                type="text"
                dir="auto"
                value={note}
                maxLength={120}
                autoComplete="off"
                disabled={busy}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            <label className="oa-input">
              <span>
                {text.brokerRefShort} <small>{text.optional}</small>
              </span>
              <input
                type="text"
                dir="ltr"
                value={reference}
                maxLength={32}
                autoComplete="off"
                disabled={busy}
                onChange={(event) => setReference(event.target.value)}
              />
            </label>
          </div>
        ) : (
          <button type="button" className="oa-link" onClick={() => setMore(true)}>
            {text.addNote}
          </button>
        ))}
      {spec.credential && (
        <CredentialFields
          form={spec.credential}
          busy={busy}
          onSubmit={(values) => void connect(spec.credential as CredentialForm, values)}
        />
      )}
      {spec.passkey && !supported && (
        <p className="oa-warn" role="status">
          {text.passkeyUnsupported}
        </p>
      )}
      {enroll && (
        <>
          <div className={`oa-key${busy ? " busy" : ""}`}>
            <span className="oa-key-ic">
              <Icon name="device" />
            </span>
            <div>
              <strong>{text.registerDevice}</strong>
              <small>{text.deviceOnce}</small>
            </div>
          </div>
          <label className="oa-input">
            <span>{text.password}</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <div className="oa-actions">
            <button
              type="button"
              className="btn primary"
              disabled={!password || busy || !supported}
              onClick={() => void register()}
            >
              {text.registerDevice}
            </button>
          </div>
        </>
      )}
      {spec.buttons.length > 0 && (
        <div className={`oa-actions${spec.buttons.length === 3 ? " three" : ""}`}>
          {spec.buttons.map((button) => (
            <button
              key={button.key}
              type="button"
              className={`btn sm ${button.primary ? "primary" : "outline"}${busy ? " is-busy" : ""}`}
              data-owner-action-button={button.key}
              disabled={busy || (spec.passkey && button.decision === "confirm" && !supported)}
              onClick={() => void decide(button)}
            >
              {spec.passkey && button.decision === "confirm" && <Icon name="fingerprint" />}
              <span>{button.label}</span>
            </button>
          ))}
        </div>
      )}
      {settled && spec.outcome && (
        <p className="oa-done" role="status" dir="auto" data-owner-action-outcome={row.status}>
          {spec.outcome}
        </p>
      )}
      {error != null && (
        <p className="oa-warn" role="alert">
          <Icon name="alert" />
          <span>{userError(error)}</span>
        </p>
      )}
    </div>
  );
}

/** Undo-only kinds: a change made without asking, in one centred line with «تراجع» (Q31). */
const NOTICE_KINDS = new Set<string>([
  "agent_model_changed",
  "agent_created",
  "supervision_created",
  "watch_changed",
  "stop_tightened",
]);
const KIND_ICON: Partial<Record<string, IconName>> = {
  grant_authority: "shield",
  set_account_limits: "scale",
  lift_restriction: "lock",
  resolve_operation: "alert",
  resume_trading: "power",
  agent_model: "cpu",
  agent_model_changed: "cpu",
  create_agent: "userPlus",
  agent_created: "userPlus",
  supervise: "eye",
  supervision_created: "eye",
  supervision_stopped: "eye",
  supervision_paused: "pause",
  trust_source: "shield",
  connect_credential: "key",
  watch_changed: "radar",
  stop_tightened: "shield",
};
const STATUS_ICON: Record<string, IconName> = {
  pending: "timer",
  confirmed: "check",
  cancelled: "close",
  expired: "timer",
  superseded: "layers",
};

function statusLabel(labels: ReturnType<typeof ownerActionText>, status: OwnerAction["status"]) {
  return {
    pending: labels.statusPending,
    confirmed: labels.statusConfirmed,
    cancelled: labels.statusCancelled,
    expired: labels.statusExpired,
    superseded: labels.statusSuperseded,
  }[status];
}

function ownerActionKindName(row: OwnerAction) {
  return ownerActionCard(row, i18n.locale).title;
}

/** Server lifetimes; shown only on resolve cards and only under one hour (Q13). */
function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const left = Math.max(0, Date.parse(until) - now);
  const s = Math.ceil(left / 1000);
  const label = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  return (
    <span className={`oa-exp${left < 60_000 ? " soon" : ""}`}>
      <span className="sr-only">{ownerActionText(i18n.locale).expiresIn}</span>
      <Icon name="timer" />
      <span className="ltr">{label}</span>
    </span>
  );
}

/** A decided or lapsed card is one line; tap for all of it; «طلب جديد» / «عرض الأحدث». */
function DecisionLine({
  row,
  kind,
  choice,
  text,
  onRenew,
  onLatest,
}: {
  row: OwnerAction;
  kind: string;
  /** The choice the owner decided with (e.g. Custom or Full delegation). */
  choice?: string;
  text: string;
  onRenew?: (row: OwnerAction) => void;
  onLatest?: (id: string) => void;
}) {
  const labels = ownerActionText(i18n.locale);
  const [open, setOpen] = useState(false);
  const supersededBy = (row as OwnerAction & { superseded_by?: string | null }).superseded_by;
  return (
    <div
      className={`oa-line st-${row.status}`}
      data-owner-action={row.id}
      data-owner-action-kind={row.kind}
      data-owner-action-status={row.status}
    >
      <span className="oa-line-ic">
        <Icon name={STATUS_ICON[row.status] ?? "check"} />
      </span>
      <button
        type="button"
        className="oa-line-body"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="oa-line-kind">
          {kind} · {statusLabel(labels, row.status)}
          {choice && (
            <>
              {" · "}
              <span dir="auto">{choice}</span>
            </>
          )}
        </span>
        <span
          className="oa-line-text"
          role="status"
          dir="auto"
          data-owner-action-outcome={row.status}
        >
          {text}
        </span>
      </button>
      {row.status === "expired" && row.kind === "resolve_operation" && onRenew && (
        <button type="button" className="btn sm ghost" onClick={() => onRenew(row)}>
          {labels.renew}
        </button>
      )}
      {row.status === "superseded" && supersededBy && onLatest && (
        <button type="button" className="btn sm ghost" onClick={() => onLatest(supersededBy)}>
          {labels.latest}
        </button>
      )}
    </div>
  );
}

function NoticeLine({
  row,
  text,
  undo,
  outcome,
  busy,
  error,
  onUndo,
}: {
  row: OwnerAction;
  text: string;
  undo?: OwnerActionButton;
  /** The settled card's own line (core settledLine), e.g. «تم التراجع: أُزيل الوكيل.». */
  outcome?: string | null;
  busy: boolean;
  error: unknown;
  onUndo: (button: OwnerActionButton) => void;
}) {
  const labels = ownerActionText(i18n.locale);
  // Only a notice that offers «تراجع» can be undone (Q31): a settled stop_tightened notice
  // was applied, never undone.
  const undone = noticeUndone(row);
  return (
    <div
      className="k-notice"
      data-owner-action={row.id}
      data-owner-action-kind={row.kind}
      data-owner-action-status={row.status}
    >
      <div className={`notice${undone ? " undone" : ""}`}>
        <Icon name={KIND_ICON[row.kind] ?? "info"} />
        <span className="nt-text" title={text} dir="auto">
          {text}
        </span>
        <time dateTime={row.created_at}>
          {new Date(row.created_at).toLocaleTimeString("en-GB", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </time>
        {undone ? (
          <span className="nt-done" role="status">
            <Icon name="undo" />
            {outcome ?? labels.undone}
          </span>
        ) : undo ? (
          <button
            type="button"
            className="nt-undo"
            data-owner-action-button={undo.key}
            disabled={busy}
            onClick={() => onUndo(undo)}
          >
            {labels.undo}
          </button>
        ) : null}
      </div>
      {error != null && (
        <p className="oa-warn" role="alert">
          {userError(error)}
        </p>
      )}
    </div>
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
