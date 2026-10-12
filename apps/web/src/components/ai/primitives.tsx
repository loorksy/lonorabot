// Modified for Lonora from Tampletgrok's AI presentation primitives; Apache-2.0.
// Pixel grid and shimmer adapted from beautifului.dev, MIT © 2026 Turbo.

import { Trans } from "@lingui/react/macro";
import { isWorking } from "@lonora/core";
import type { ReactNode } from "react";
import type { Event, Run } from "../../lib/api";
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
      {run.status === "waiting_input" ? (
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

export function AgentActivity({ events }: { events: Event[] }) {
  const recent = events
    .filter((event) => event.kind === "run.progress" || event.kind === "run.model")
    .slice(-4);
  if (!recent.length) return null;
  return (
    <div className="progress" aria-live="polite">
      {recent.map((event) => (
        <p key={event.cursor}>
          <Trans>Processing the task</Trans>
          {event.payload.provider && (
            <>
              {" "}
              ·{" "}
              <bdi>
                {String(event.payload.provider)} / {String(event.payload.model ?? "")}
              </bdi>
            </>
          )}
        </p>
      ))}
    </div>
  );
}
