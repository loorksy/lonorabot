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
        <div key={event.cursor}>
          <div className="row">
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
          {typeof event.payload.code === "string" &&
            /^[a-z][a-z0-9_]{0,119}$/.test(event.payload.code) && (
              <code
                dir="ltr"
                className="muted"
                style={{ display: "block", overflowWrap: "anywhere" }}
              >
                {event.payload.code}
              </code>
            )}
        </div>
      ))}
    </details>
  );
}
