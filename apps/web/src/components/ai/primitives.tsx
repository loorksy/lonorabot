// Modified for Lonora from Tampletgrok's AI presentation primitives; Apache-2.0.
// Pixel grid and shimmer adapted from beautifului.dev, MIT © 2026 Turbo.

import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { isWorking } from "@lonora/core";
import type { ReactNode } from "react";
import type { Agent, Event, Run } from "../../lib/api";
import { AgentAvatar } from "./AgentAvatar";
import "./beautiful-ui.css";

const CHEVRON_CELLS = Array.from({ length: 9 }, (_, index) => {
  const row = Math.floor(index / 3);
  const column = index % 3;
  return { key: `${row}:${column}`, delay: (column + Math.abs(row - 1)) * 90 };
});

/** Tampletgrok's shimmer presentation, with the label supplied by the real runtime state. */
export function Shimmer({ children }: { children: ReactNode }) {
  return <span className="lonora-shimmer">{children}</span>;
}

/** Accessible pixel-grid activity indicator; it never invents a running task. */
export function LoadingState({ label, indicator }: { label: ReactNode; indicator?: ReactNode }) {
  return (
    <span role="status" className="working lonora-loading-state">
      {indicator ?? (
        <span className="lonora-pixel-grid" aria-hidden="true">
          {CHEVRON_CELLS.map((cell) => (
            <span key={cell.key} style={{ animationDelay: `${cell.delay}ms` }} />
          ))}
        </span>
      )}
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
  void events;
  const working = runs.filter((run) => isWorking(run.status));
  if (!working.length) return null;
  return (
    <div className="progress template-active-agents" aria-live="polite">
      {working.map((run) => {
        const agent = agents.find((item) => item.id === run.agent_id);
        const name = agent?.name ?? t`Agent`;
        return (
          <div key={run.id} data-progress-run-id={run.id}>
            <LoadingState
              indicator={agent ? <AgentAvatar agent={agent} working /> : undefined}
              label={
                <bdi>{run.status === "queued" ? t`${name} is queued` : t`${name} is working`}</bdi>
              }
            />
          </div>
        );
      })}
    </div>
  );
}
