import { i18n } from "@lingui/core";
import type { DeviceChallenge, OwnerAction, OwnerActionDecision } from "@lonora/contracts";
import {
  brokerCardFailed,
  mergeOwnerAction,
  modeChangeLine,
  OWNER_ACTION_CHANGED,
  type OwnerActionButton,
  type OwnerActionOption,
  ownerActionCard,
  ownerActionChoices,
  ownerActionChoose,
  ownerActionLive,
  ownerActionStatus,
  ownerActionText,
  rereadOwnerAction,
  type SecretForm,
  SLOT_OWNER_ACTION_KINDS,
  submitSecret,
  webDeviceProof,
  webDeviceSupported,
} from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { useToast } from "../../shell/Toast";

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
 * card asks for the passkey (registering this device inline the first time); its
 * switches go with that tap. Every tap goes to the owner-session route, which
 * re-validates.
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
  const toast = useToast();
  const { refresh } = useClient();
  const spec = ownerActionCard(row, locale);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
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
    if (button.trading_mode) body.trading_mode = button.trading_mode;
    if (button.outcome) {
      body.outcome = button.outcome;
    }
    const updated = await api.post<OwnerAction>(`/owner-actions/${row.id}/decision`, body);
    waiting.current = null;
    if (button.trading_mode && updated.result.trading_mode) {
      const applied = updated.result.trading_mode === "full" ? "full" : "ask";
      const name = updated.facts.agent?.name ?? row.facts.agent?.name ?? "";
      toast(modeChangeLine(name, applied, updated.result.withdrawn ?? 0, locale), {
        type: "success",
      });
      refresh();
    }
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
  async function save(values: Record<string, string>) {
    setBusy(true);
    setError(undefined);
    try {
      // The values go only to the card's own route, which stores them encrypted.
      const updated = await submitSecret(
        (path, body) => api.post<OwnerAction>(path, body),
        row.id,
        values,
      );
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
  const supersededBy = (row as OwnerAction & { superseded_by?: string | null }).superseded_by;
  // Only a kind outside the fixed cards folds into one line once settled (W-AUTH and the team
  // stack delete those kinds); a fixed card is never folded (10.2.2).
  if (ownerActionFolds(row) && !inSheet)
    return (
      <DecisionLine
        row={row}
        kind={spec.title}
        // A signed grant names Full delegation (the core spec's line for the signed terms).
        choice={spec.lines.find((line) => line === text.delegationFull)}
        text={spec.outcome ?? spec.title}
        supersededBy={supersededBy}
        onLatest={onLatest}
      />
    );
  // A broker card whose connection failed never shows its outcome in the success tint.
  const failed = brokerCardFailed(row);
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
      {spec.secret && (
        <SecretFields form={spec.secret} busy={busy} onSubmit={(values) => void save(values)} />
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
        <p
          className={`oa-done${failed ? " bad" : ""}`}
          role="status"
          dir="auto"
          data-owner-action-outcome={row.status}
          data-owner-action-failed={failed || undefined}
        >
          {spec.outcome}
        </p>
      )}
      {/* A card a newer one replaced (renewed, or superseded) shows the newer one; only an
          expired Settle card that was not renewed yet asks again. */}
      {supersededBy
        ? onLatest && (
            <div className="oa-actions">
              <button
                type="button"
                className="btn sm outline"
                onClick={() => onLatest(supersededBy)}
              >
                {text.latest}
              </button>
            </div>
          )
        : row.status === "expired" &&
          row.kind === "settle_operation" &&
          onRenew && (
            <div className="oa-actions">
              <button type="button" className="btn sm outline" onClick={() => onRenew(row)}>
                {text.renew}
              </button>
            </div>
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

const KIND_ICON: Partial<Record<string, IconName>> = {
  settle_operation: "alert",
  supervision_paused: "pause",
  secret: "key",
};
/** The fixed cards among the owner-action kinds (10.3: Settle, Secret, Mandate), the kinds a
 * trusted slot can name. */
const FIXED_KINDS = new Set<string>(Object.values(SLOT_OWNER_ACTION_KINDS));

/** A settled card of a kind outside the fixed cards: one line, until W-AUTH and the team stack
 * delete those kinds. A fixed card keeps its frame (10.2.2). */
export function ownerActionFolds(row: OwnerAction): boolean {
  return !ownerActionLive(row) && !FIXED_KINDS.has(row.kind);
}

const STATUS_ICON: Record<string, IconName> = {
  pending: "timer",
  confirmed: "check",
  cancelled: "close",
  expired: "timer",
  superseded: "layers",
};

/** A decided or lapsed card of an old kind is one line; tap for all of it; «عرض الأحدث». */
function DecisionLine({
  row,
  kind,
  choice,
  text,
  supersededBy,
  onLatest,
}: {
  row: OwnerAction;
  kind: string;
  /** The choice the owner decided with (e.g. Custom or Full delegation). */
  choice?: string;
  text: string;
  supersededBy?: string | null;
  onLatest?: (id: string) => void;
}) {
  const labels = ownerActionText(i18n.locale);
  const [open, setOpen] = useState(false);
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
          {kind} · {ownerActionStatus(row, i18n.locale)}
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
      {row.status === "superseded" && supersededBy && onLatest && (
        <button type="button" className="btn sm ghost" onClick={() => onLatest(supersededBy)}>
          {labels.latest}
        </button>
      )}
    </div>
  );
}

/** A Secret card's form: values stay in this component until they are posted to the card's
 * route, and are cleared as soon as they are sent. */
function SecretFields({
  form,
  busy,
  onSubmit,
}: {
  form: SecretForm;
  busy: boolean;
  onSubmit: (values: Record<string, string>) => void;
}) {
  const empty = () => Object.fromEntries(form.fields.map((field) => [field.key, ""]));
  const [values, setValues] = useState<Record<string, string>>(empty);
  return (
    <form
      className="lonora-owner-action-notes"
      data-owner-action-form="secret"
      onSubmit={(event) => {
        event.preventDefault();
        // An optional field left empty is not sent.
        const sent = Object.fromEntries(Object.entries(values).filter(([, value]) => value.trim()));
        setValues(empty());
        onSubmit(sent);
      }}
    >
      {form.fields.map((field) => (
        <label key={field.key}>
          <span dir="auto">{field.label}</span>
          <input
            name={field.key}
            type={field.type}
            dir="ltr"
            required={field.required}
            // Never offered to, or filled from, a password manager: not a Lonora login.
            autoComplete="one-time-code"
            spellCheck={false}
            value={values[field.key] ?? ""}
            disabled={busy}
            onChange={(event) => setValues((old) => ({ ...old, [field.key]: event.target.value }))}
          />
        </label>
      ))}
      <div className="oa-actions">
        <button
          type="submit"
          className={`btn sm primary${busy ? " is-busy" : ""}`}
          disabled={busy}
          data-owner-action-button="save"
        >
          {form.submit}
        </button>
      </div>
    </form>
  );
}
