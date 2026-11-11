import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { InputAnswer, InputRequest, Journal } from "@lonora/contracts";
import {
  type ActivityCall,
  activityCallLabel,
  financialBoundaryError,
  type OrderLineState,
  orderLineAction,
  orderLineState,
  peerOutcome,
} from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Message, Resource, Run } from "../lib/api";
import { userError } from "../lib/user_error";
import { md } from "./Markdown";

/* Cards that live inside the conversation's Message frame: the agent error card, the question
   card, the order line and its sheet, and the agent's steps (reference 3761-3775, 5491-5515,
   5866-5878, 8178-8245). */

/** Q22: the card reflects the provider's actual error family. */
export type FailureFamily = "quota" | "rate" | "timeout" | "model" | "other";
export function failureOf(run: Run): { family: FailureFamily; retryAfter: number | null } {
  const failure = (
    run as Run & { failure?: { family?: FailureFamily; retry_after_seconds?: number | null } }
  ).failure;
  if (failure?.family)
    return { family: failure.family, retryAfter: failure.retry_after_seconds ?? null };
  const code = run.error_code ?? "";
  if (/quota|budget|insufficient|billing/.test(code)) return { family: "quota", retryAfter: null };
  if (/rate/.test(code)) return { family: "rate", retryAfter: 30 };
  if (/timeout|timed_out|deadline/.test(code)) return { family: "timeout", retryAfter: null };
  if (/model|provider/.test(code)) return { family: "model", retryAfter: null };
  return { family: "other", retryAfter: null };
}

const ERROR_ICON: Record<FailureFamily, IconName> = {
  quota: "chart",
  rate: "clock",
  timeout: "alert",
  model: "cpu",
  other: "alert",
};

export function AgentErrorCard({
  run,
  onRetry,
  onFix,
}: {
  run: Run;
  onRetry: (run: Run) => Promise<void>;
  onFix: (family: FailureFamily) => void;
}) {
  const { family, retryAfter } = failureOf(run);
  const [until] = useState(() => (retryAfter ? Date.parse(run.updated_at) + retryAfter * 1000 : 0));
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    if (until <= Date.now()) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [until]);
  const left = until ? Math.max(0, Math.ceil((until - now) / 1000)) : 0;
  const title = {
    quota: t`The model provider's quota ran out`,
    rate: t`Too many requests in a short time`,
    timeout: t`The reply timed out`,
    model: t`The model is not available right now`,
    other: t`The agent could not reply`,
  }[family];
  const text = {
    // Q22 (D4): Lonora sets no spend cap; the refusal is the provider's own quota.
    quota: t`The model provider refused the request for quota on its account. Add credit with the provider, choose another model, or retry once it resets.`,
    rate: t`Many requests were sent within a minute. Wait a little, then try again.`,
    timeout: t`The reply did not arrive in time; the connection may be weak.`,
    model: t`The model provider could not be reached. Try another model or retry shortly.`,
    other: userError({ code: run.error_code }),
  }[family];
  const fix = family === "quota" ? t`View usage` : family === "model" ? t`Change the model` : null;
  return (
    <div className="err-card" role="alert" data-failure={family}>
      <div className="err-top">
        <span className="err-ic">
          <Icon name={ERROR_ICON[family]} />
        </span>
        <strong>{title}</strong>
      </div>
      <p>{text}</p>
      {/* Retry only re-asks the provider: a reply that failed for another reason (it may
          have touched the executor) never gets a generic retry. */}
      {family !== "other" && (
        <div className="err-actions">
          {fix && (
            <button type="button" className="btn primary small" onClick={() => onFix(family)}>
              {fix}
            </button>
          )}
          <button
            type="button"
            className={`btn ${fix ? "outline" : "primary"} small`}
            disabled={left > 0 || busy}
            onClick={() => {
              setBusy(true);
              setError(undefined);
              void onRetry(run)
                .catch(setError)
                .finally(() => setBusy(false));
            }}
          >
            <Icon name="refresh" />
            <span>{left ? t`Retry in ${left} s` : t`Retry`}</span>
          </button>
        </div>
      )}
      {error != null && <p>{userError(error)}</p>}
    </div>
  );
}

/** «سؤال من الوكيل»: option rows + a custom answer; single use. */
export function QuestionCard({
  request,
  onAnswer,
  onCustom,
}: {
  request: InputRequest;
  onAnswer: (answer: InputAnswer, label: string) => Promise<void>;
  /** A custom answer is a normal message replying to the question (the run reads it). */
  onCustom: (text: string) => Promise<void>;
}) {
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);
  // The chosen row until the server's own answer arrives, then the server's.
  const [picked, setPicked] = useState<string | null>(null);
  const chosen = request.status !== "pending" ? request.selected_choice_id : picked;
  const open = request.status === "pending" && !picked;
  return (
    <div className="mcard" data-input-request={request.id} data-question-id={request.id}>
      <div className="mcard-kicker">
        <Icon name="chat" />
        <Trans>Question from the agent</Trans>
      </div>
      <strong dir="auto">{request.question}</strong>
      {/* biome-ignore lint/a11y/useSemanticElements: the reference's answer rows */}
      <div className="opt-list" role="group" aria-label={t`Answers`}>
        {request.choices.map((choice) => (
          <button
            key={choice.id}
            type="button"
            className={`opt-row${chosen === choice.id ? " on" : ""}`}
            aria-pressed={chosen === choice.id}
            disabled={busy || !open}
            onClick={() => {
              setBusy(true);
              setPicked(choice.id);
              void onAnswer(
                { run_id: request.run_id, question_id: request.id, choice_id: choice.id },
                choice.label,
              )
                .catch(() => setPicked(null))
                .finally(() => setBusy(false));
            }}
          >
            <span dir="auto">{choice.label}</span>
            <Icon name={chosen === choice.id ? "check" : "chev"} />
          </button>
        ))}
      </div>
      {open && (
        <form
          className="mcard-form"
          onSubmit={(event) => {
            event.preventDefault();
            const text = custom.trim();
            if (!text) return;
            setBusy(true);
            void onCustom(text).finally(() => setBusy(false));
          }}
        >
          <input
            name="custom"
            placeholder={t`Or write another answer`}
            aria-label={t`Another answer`}
            autoComplete="off"
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
          />
          <button
            type="submit"
            className="icon send-sm"
            aria-label={t`Send the answer`}
            disabled={busy}
          >
            <Icon name="arrowUp" />
          </button>
        </form>
      )}
    </div>
  );
}

/* ---- Orders (Q30): the server's operation states under the reference's names, from the
   one shared helper (core orderLineState: the executor's real TradeResult fields). «منفَّذ»
   only with evidence (a broker ticket or a verified state, or the owner's attestation). */
export type OrderState = OrderLineState;
export function orderState(row: Journal): OrderState {
  return orderLineState(row).state;
}
const ORDER_TONE: Record<OrderState, string> = {
  requested: "wait",
  sent: "wait",
  accepted: "wait",
  partial: "ok",
  filled: "ok",
  rejected: "bad",
  cancelled: "off",
  blocked: "off",
  uncertain: "warn",
};
export function orderLabel(state: OrderState) {
  return {
    requested: t({ message: "Requested", context: "order state" }),
    sent: t({ message: "Sent", context: "order state" }),
    accepted: t({ message: "Accepted by the broker", context: "order state" }),
    partial: t({ message: "Partially filled", context: "order state" }),
    filled: t({ message: "Filled", context: "order state" }),
    rejected: t({ message: "Rejected", context: "order state" }),
    cancelled: t({ message: "Cancelled", context: "order state" }),
    blocked: t({ message: "Blocked before sending", context: "order state" }),
    uncertain: t({ message: "Unconfirmed", context: "order state" }),
  }[state];
}
export function OrderBadge({ state }: { state: OrderState }) {
  const icon: IconName =
    state === "filled" || state === "partial"
      ? "check"
      : state === "rejected"
        ? "close"
        : state === "cancelled" || state === "blocked"
          ? "minus"
          : state === "uncertain"
            ? "alert"
            : "hourglass";
  return (
    <span className={`od-st t-${ORDER_TONE[state]}`}>
      <Icon name={icon} />
      <span>{orderLabel(state)}</span>
    </span>
  );
}
export function OrderLine({ row, onOpen }: { row: Journal; onOpen: (row: Journal) => void }) {
  const line = orderLineState(row);
  const state = line.state;
  const action = orderLineAction(row.request, i18n.locale);
  const symbol = String(row.request.symbol ?? "");
  const limit = row.request.price != null ? String(row.request.price) : null;
  const summary = `${action.label}${action.volume ? ` ${action.volume}` : ""} ${symbol}`;
  return (
    <button
      type="button"
      className={`od-chat s-${state}`}
      data-operation-id={row.operation_id}
      data-order-state={state}
      aria-label={t`Order ${summary}: ${orderLabel(state)}. Show details`}
      onClick={() => onOpen(row)}
    >
      <span className="od-chat-ic">
        <Icon
          name={
            action.direction === "down" ? "trendDown" : action.direction === "up" ? "trend" : "edit"
          }
        />
      </span>
      <span className="od-chat-body">
        <strong>
          {action.label}
          {action.volume && (
            <>
              {" "}
              <span className="ltr">{action.volume}</span>
            </>
          )}{" "}
          <bdi>{symbol}</bdi>
        </strong>
        <small>
          {limit ? (
            <>
              <Trans>Limit at</Trans> <span className="ltr">{limit}</span>
            </>
          ) : action.direction ? (
            <Trans>At market price</Trans>
          ) : null}
          {line.fill_price && (
            <>
              {" · "}
              <span className="ltr">{line.fill_price}</span>
            </>
          )}
        </small>
      </span>
      <OrderBadge state={state} />
    </button>
  );
}

/** The order sheet: the timeline, the evidence and the technical details (reference odSheet). */
export function OrderSheetBody({ row, onResolve }: { row: Journal; onResolve?: () => void }) {
  const line = orderLineState(row);
  const state = line.state;
  // The shared timeline (core orderLineState): a never-sent order reads Requested → Blocked
  // before sending, never Sent or Accepted.
  const LADDER: OrderState[] = ["requested", "sent", "accepted", "filled"];
  const final = ["filled", "partial", "rejected", "cancelled", "blocked", "uncertain"];
  const next = final.includes(state) ? [] : LADDER.slice(LADDER.indexOf(state) + 1);
  const tone = (step: OrderState) =>
    step === "rejected"
      ? "on bad"
      : step === "cancelled" || step === "blocked"
        ? "on off"
        : step === "uncertain"
          ? "warn"
          : "on";
  const ticket = line.ticket ?? "—";
  const time = (iso?: string | null) =>
    iso ? new Date(iso).toLocaleTimeString("en-GB", { hour12: false }) : "…";
  const code = row.result?.code ? String(row.result.code) : null;
  const details = (row.result?.details ?? {}) as Record<string, unknown>;
  // A rejection or a block names its own reason; never a generic "try again" on money.
  const reason =
    financialBoundaryError(code, i18n.locale) ??
    (typeof details.description === "string" && details.description ? details.description : null);
  return (
    <div className="od-sheet">
      <ol className="od-line" data-steps={line.steps.join(" ")}>
        {line.steps.map((step) => (
          <li key={step} className={tone(step)}>
            <i />
            <span>{orderLabel(step)}</span>
            {step === "uncertain" ? (
              <time>
                <Trans>No answer from the broker</Trans>
              </time>
            ) : (
              <time className="ltr">
                {time(step === "requested" ? row.submitted_at : row.updated_at)}
              </time>
            )}
          </li>
        ))}
        {next.map((step) => (
          <li key={step} className="next">
            <i />
            <span>{orderLabel(step)}</span>
            <time>…</time>
          </li>
        ))}
      </ol>
      {state === "filled" || state === "partial" ? (
        <div className="od-ev ok">
          <Icon name="check" />
          <span>
            {line.evidence === "owner" ? (
              <Trans>Recorded from your statement, not broker confirmation</Trans>
            ) : (
              <>
                <Trans>Fill evidence: ticket</Trans> <b className="ltr">{ticket}</b>
                {line.fill_price && (
                  <>
                    {" · "}
                    <span className="ltr">{line.fill_price}</span>
                  </>
                )}
                {state === "partial" && line.filled_volume && (
                  <>
                    {" · "}
                    <span className="ltr">
                      {line.filled_volume}/{line.requested_volume ?? "?"}
                    </span>
                  </>
                )}
              </>
            )}
          </span>
        </div>
      ) : state === "uncertain" ? (
        <div className="od-ev warn">
          <Icon name="alert" />
          <span>
            <Trans>
              The broker's confirmation did not arrive; «Filled» is never shown before the evidence.
            </Trans>
          </span>
        </div>
      ) : state === "rejected" ? (
        <div className="od-ev bad">
          <Icon name="close" />
          <span data-order-reason="rejected">
            <Trans>The broker rejected the order</Trans>
            {reason && (
              <>
                {" · "}
                <bdi>{reason}</bdi>
              </>
            )}
          </span>
        </div>
      ) : state === "cancelled" || state === "blocked" ? (
        <div className="od-ev off">
          <Icon name="minus" />
          <span data-order-reason={state}>
            {line.not_sent ? <Trans>Not sent to the broker</Trans> : orderLabel("cancelled")}
            {line.not_sent && reason && (
              <>
                {" · "}
                <bdi>{reason}</bdi>
              </>
            )}
          </span>
        </div>
      ) : (
        <div className="od-ev wait">
          <Icon name="hourglass" />
          <span>
            <Trans>Waiting for the broker's answer…</Trans>
          </span>
        </div>
      )}
      {state === "uncertain" && onResolve && (
        <div className="oa-actions">
          <button type="button" className="btn sm" onClick={onResolve}>
            <Trans>Resolve the operation</Trans>
          </button>
        </div>
      )}
      <details className="od-tech">
        <summary>
          <Icon name="down" />
          <span>
            <Trans>Technical details</Trans>
          </span>
        </summary>
        <dl>
          <div>
            <dt>
              <Trans>Operation id</Trans>
            </dt>
            <dd className="ltr">{row.operation_id}</dd>
          </div>
          <div>
            <dt>
              <Trans>Broker ticket</Trans>
            </dt>
            <dd className="ltr">{ticket}</dd>
          </div>
          <div>
            <dt>
              <Trans>Account</Trans>
            </dt>
            <dd className="ltr">{row.account_id}</dd>
          </div>
          {row.result?.string_code != null && (
            <div>
              <dt>
                <Trans>Broker return code</Trans>
              </dt>
              <dd className="ltr">{String(row.result.string_code)}</dd>
            </div>
          )}
        </dl>
      </details>
    </div>
  );
}

/** The agent's steps above the answer; live while it works, then one folded line. */
export function Steps({
  calls,
  running,
  seconds,
  defaultOpen,
}: {
  calls: ActivityCall[];
  running: boolean;
  seconds: number;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState<boolean | null>(null);
  if (!calls.length) return null;
  const shown = running || (open ?? defaultOpen);
  const live = [...calls].reverse().find((call) => call.status === "running");
  const label = (call: ActivityCall) => activityCallLabel(call, i18n.locale);
  const n = calls.length;
  return (
    <div className={`steps${shown ? " open" : ""}${running ? " running" : ""}`}>
      <button
        type="button"
        className="steps-head"
        aria-expanded={shown}
        onClick={() => setOpen(!shown)}
      >
        {running && live ? (
          <>
            <span className="spin" />
            <span>{label(live)}…</span>
          </>
        ) : (
          <>
            <span className="st-done">
              <Icon name="check" />
            </span>
            <span>
              {n === 1 ? t`One step` : n === 2 ? t`Two steps` : t`${n} steps`}
              {seconds > 0 && ` · ${t`${seconds} s`}`}
            </span>
          </>
        )}
        <span className="steps-chev">
          <Icon name="down" />
        </span>
      </button>
      <ol className="steps-list">
        {calls.map((call) => (
          <li key={call.id} className={call.status === "running" ? "run" : "done"}>
            <span className="st-ic">
              {call.status === "running" ? <span className="spin" /> : <Icon name="check" />}
            </span>
            <span className="st-t">
              <b>{label(call)}</b>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** The message ids a peer exchange (agent ↔ agent) is shown on, in both conversations. */
export function peersByMessage(peers: Resource[]): Map<string, Resource> {
  const out = new Map<string, Resource>();
  for (const peer of peers) {
    const payload = peer.payload;
    for (const id of [
      payload.source_message_id,
      payload.target_message_id,
      payload.source_outcome_message_id,
      payload.target_outcome_message_id,
      ...(Array.isArray(payload.source_outcome_message_ids)
        ? payload.source_outcome_message_ids
        : []),
    ])
      if (typeof id === "string") out.set(id, peer);
  }
  return out;
}

/** An actual persisted request between two agents, or its returned result, with links to
    both continuous conversations (the reference's card frame). */
export function PeerCard({ message, peer, run }: { message: Message; peer: Resource; run?: Run }) {
  const payload = peer.payload;
  const request =
    payload.source_message_id === message.id || payload.target_message_id === message.id;
  const wrapped = peerOutcome(message.content);
  const side = (a: unknown, b: unknown) => String((request ? a : b) ?? "");
  const from = {
    id: side(payload.source_agent_id, payload.target_agent_id),
    name: side(payload.source_agent_name, payload.target_agent_name),
    thread: side(payload.source_thread_id, payload.target_thread_id),
  };
  const to = {
    id: side(payload.target_agent_id, payload.source_agent_id),
    name: side(payload.target_agent_name, payload.source_agent_name),
    thread: side(payload.target_thread_id, payload.source_thread_id),
  };
  const status = wrapped.status ?? run?.status ?? String(payload.status ?? "queued");
  const who = (party: typeof from) => {
    const name = <bdi>{party.name || t`Agent`}</bdi>;
    return party.id ? (
      <Link to={`/app/${encodeURIComponent(party.id)}?thread=${encodeURIComponent(party.thread)}`}>
        {name}
      </Link>
    ) : (
      name
    );
  };
  const label =
    status === "cancelled"
      ? t({ message: "Cancelled", context: "task state" })
      : status === "failed"
        ? t({ message: "Failed", context: "task state" })
        : status === "completed"
          ? t({ message: "Completed", context: "task state" })
          : status === "limited"
            ? t`Stopped at its work limit`
            : ["running", "leased"].includes(status)
              ? t`Working…`
              : t({ message: "Queued", context: "task state" });
  return (
    <div
      className="mcard peer-card"
      data-peer-message-id={peer.id}
      data-peer-kind={request ? "request" : "outcome"}
    >
      <div className="mcard-kicker">
        <Icon name="users" />
        <Trans>Agent collaboration</Trans>
      </div>
      <div className="peer-who">
        {who(from)}
        <Icon name="back" className="flip" />
        {who(to)}
      </div>
      {!(status === "cancelled" && wrapped.body === "cancelled") && (
        <div className="md" dir="auto">
          {md(wrapped.body, null)}
        </div>
      )}
      <span className="mcard-sub">{label}</span>
    </div>
  );
}
