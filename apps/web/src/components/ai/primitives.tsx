// Modified for Lonora from Tampletgrok's AI presentation primitives; Apache-2.0.
// Pixel grid and shimmer adapted from beautifului.dev, MIT © 2026 Turbo.

import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { isWorking } from "@lonora/core";
import type { ReactNode } from "react";
import type { Agent, Event, Run } from "../../lib/api";
import { runActivity } from "../../lib/run-activity";
import { AgentAvatar } from "./AgentAvatar";
import "./beautiful-ui.css";

/** Tampletgrok's shimmer presentation, with the label supplied by the real runtime state. */
export function Shimmer({ children }: { children: ReactNode }) {
  return <span className="lonora-shimmer">{children}</span>;
}

/** Activity uses the actual avatar when available; no separate grid animation. */
export function LoadingState({ label, indicator }: { label: ReactNode; indicator?: ReactNode }) {
  return (
    <span role="status" className="working lonora-loading-state">
      {indicator}
      <Shimmer>{label}</Shimmer>
    </span>
  );
}

export function WorkingIndicator({ run }: { run?: Run }) {
  if (!run) return null;
  if (isWorking(run.status))
    return (
      <LoadingState
        label={run.status === "queued" ? <Trans>Queued</Trans> : <Trans>Working</Trans>}
      />
    );
  return (
    <span className="working" role="status">
      {run.status === "completed" && run.model_metadata.reply_outcome === "silent" ? (
        <Trans>No reply needed</Trans>
      ) : run.status === "waiting_input" ? (
        <Trans>Waiting for your reply</Trans>
      ) : run.status === "waiting_takeover" ? (
        <Trans>Waiting for handover</Trans>
      ) : run.status === "failed" ? (
        <Trans>Failed</Trans>
      ) : run.status === "cancelled" ? (
        <Trans>Cancelled</Trans>
      ) : (
        <Trans>Completed</Trans>
      )}
    </span>
  );
}

export function AgentActivity({
  events,
  runs,
  agents,
}: {
  events: Event[];
  runs: Run[];
  agents: Agent[];
}) {
  const working = runs.filter((run) => isWorking(run.status));
  if (!working.length) return null;
  return (
    <div className="progress template-active-agents" aria-live="polite">
      {working.map((run) => {
        const agent = agents.find((item) => item.id === run.agent_id);
        const name = agent?.name ?? t`Agent`;
        const activity = runActivity(run, events);
        const labels: Record<string, string> = {
          learning: t`Learning`,
          sending: t`Sending…`,
          thinking: t`Thinking`,
          writing: t`Writing`,
          searching: t`Searching`,
          analyzing: t`Analyzing`,
          executing: t`Executing`,
          inspecting: t`Reading`,
          waiting: t`Queued`,
        };
        return (
          <div key={run.id} data-progress-run-id={run.id}>
            <LoadingState
              indicator={agent ? <AgentAvatar agent={agent} working state={activity} /> : undefined}
              label={
                <bdi>
                  {name} · {labels[activity] ?? t`Thinking`}
                </bdi>
              }
            />
          </div>
        );
      })}
    </div>
  );
}
