import { Trans } from "@lingui/react/macro";
import type { Event } from "../../lib/api";
export function AgentActivity({ events }: { events: Event[] }) {
  const recent = events
    .filter((e) => e.kind === "run.progress" || e.kind === "run.model")
    .slice(-4);
  if (!recent.length) return null;
  return (
    <div className="progress" aria-live="polite">
      {recent.map((e) => (
        <p key={e.cursor}>
          <Trans>Processing the task</Trans>
          {e.payload.provider && (
            <>
              {" "}
              ·{" "}
              <bdi>
                {String(e.payload.provider)} / {String(e.payload.model ?? "")}
              </bdi>
            </>
          )}
        </p>
      ))}
    </div>
  );
}
