import { Trans } from "@lingui/react/macro";
import type { Event } from "../lib/api";
export function ToolActivityDisclosure({ events }: { events: Event[] }) {
  const calls = new Map<string, Event>();
  for (const event of events) {
    if (event.kind.startsWith("tool.")) {
      calls.set(`${event.run_id ?? ""}:${event.payload.call_id ?? event.cursor}`, event);
    }
  }
  const activity = [...calls.values()].slice(-12);
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
            {event.kind.includes("cancel") ? (
              <Trans>Cancelled</Trans>
            ) : event.kind.includes("fail") || event.payload.ok === false ? (
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
