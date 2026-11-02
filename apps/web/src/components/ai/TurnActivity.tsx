import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { type ActivityPhase, isWorking, turnActivity } from "@lonora/core";
import { ChevronDown } from "lucide-react";
import type { Agent, Event, Run } from "../../lib/api";
import { AgentAvatar } from "./AgentAvatar";
import "./agent-status.css";

/** Compact, turn-scoped observations. Never model reasoning or guessed progress. */
export function TurnActivity({
  run,
  agent,
  events,
  connected = true,
}: {
  run: Run;
  agent?: Agent;
  events: Event[];
  connected?: boolean;
}) {
  const { i18n } = useLingui();
  const activity = turnActivity(run, events);
  const labels: Record<ActivityPhase, string> = {
    learning: t`Learning`,
    sending: t`Sending…`,
    queued: t`Queued`,
    preparing: t`Preparing`,
    thinking: t`Thinking`,
    searching: t`Searching`,
    reading: t`Reading`,
    analyzing: t`Analyzing`,
    executing: t`Executing`,
    writing: t`Writing`,
    waiting_input: t`Waiting for your reply`,
    waiting_external: t`Waiting for handover`,
    completed: t`Completed`,
    failed: t`Failed`,
    cancelled: t`Cancelled`,
  };
  const active = isWorking(run.status);
  const reconnecting = active && !connected;
  const attention = reconnecting || ["waiting_input", "waiting_external"].includes(activity.phase);
  const tone =
    activity.phase === "failed"
      ? "error"
      : attention
        ? "attention"
        : activity.phase === "completed"
          ? "success"
          : active
            ? "active"
            : "quiet";
  const label = reconnecting ? t`Reconnecting` : labels[activity.phase];
  const indicator = agent ? (
    <AgentAvatar
      agent={agent}
      state={reconnecting ? "connecting" : activity.avatar}
      working={active}
    />
  ) : undefined;
  const compact = (
    <span
      className="lonora-turn-signal"
      data-progress-run-id={active ? run.id : undefined}
      data-turn-run-id={run.id}
      data-activity-phase={reconnecting ? "reconnecting" : activity.phase}
      data-tone={tone}
      data-active={active && !reconnecting}
    >
      {indicator}
      <span className="lonora-turn-label" role="status" aria-live="polite" aria-atomic="true">
        {agent?.name && <bdi className="lonora-turn-name">{agent.name}</bdi>}
        <span className="lonora-turn-phase">
          <i className="lonora-status-dot" aria-hidden="true" />
          <bdi>{label}</bdi>
        </span>
      </span>
      {activity.calls.length > 0 && (
        <ChevronDown className="lonora-turn-expand" size={16} aria-hidden="true" />
      )}
    </span>
  );
  if (!activity.calls.length) return <div className="template-turn-activity">{compact}</div>;
  return (
    <details className="template-turn-activity">
      <summary>{compact}</summary>
      <div className="template-turn-steps">
        {activity.calls.map((call) => (
          <div key={call.id} className="template-turn-step">
            <code dir="ltr">{call.name}</code>
            <span>
              {call.status === "running"
                ? t`Running`
                : call.status === "completed"
                  ? t`Completed`
                  : call.status === "failed"
                    ? t`Failed`
                    : call.status === "cancelled"
                      ? t`Cancelled`
                      : t`Interrupted`}
            </span>
            {(call.completed_at ?? call.started_at) && (
              <time dateTime={call.completed_at ?? call.started_at}>
                {new Date(call.completed_at ?? call.started_at ?? "").toLocaleTimeString(
                  i18n.locale,
                  { hour: "2-digit", minute: "2-digit", second: "2-digit" },
                )}
              </time>
            )}
          </div>
        ))}
        {reconnecting && (
          <p>
            <Trans>Reconnecting</Trans>
          </p>
        )}
      </div>
    </details>
  );
}
