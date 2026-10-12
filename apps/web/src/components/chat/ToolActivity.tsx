import { Trans } from "@lingui/react/macro";
import type { Event } from "../../lib/api";
export function ToolActivity({ events }: { events: Event[] }) {
  const activity = events.filter((e) => e.kind.startsWith("tool.")).slice(-12);
  if (!activity.length) return null;
  return (
    <details className="activity">
      <summary>
        <Trans>Tool activity</Trans> <span className="badge">{activity.length}</span>
      </summary>
      {activity.map((event) => (
        <div className="row" key={event.cursor}>
          <code>{String(event.payload.name ?? event.payload.tool ?? "")}</code>
          <span>
            {event.kind.includes("fail") ? (
              <Trans>Failed</Trans>
            ) : event.kind.includes("complete") || event.kind.includes("result") ? (
              <Trans>Completed</Trans>
            ) : (
              <Trans>Running</Trans>
            )}
          </span>
        </div>
      ))}
    </details>
  );
}
