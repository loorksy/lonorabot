import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";

type EconomicEvent = {
  id: string;
  name: string;
  currency: string;
  scheduled_at: string;
  impact: string;
  actual: string | null;
  forecast: string | null;
  source: string;
};
export function EconomicCalendar() {
  const [rows, setRows] = useState<EconomicEvent[]>([]);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void api.get<EconomicEvent[]>("/market/calendar").then(setRows).catch(setError);
  }, []);
  return (
    <details className="card">
      <summary>
        <Trans>Economic calendar</Trans>
      </summary>
      {error != null && <p role="alert">{userError(error)}</p>}
      {!rows.length && (
        <p className="muted">
          <Trans>Add an economic calendar feed in Integrations to load events.</Trans>
        </p>
      )}
      {rows.map((e) => (
        <div className="calendar-row" key={e.id}>
          <time>{new Date(e.scheduled_at).toLocaleString()}</time>
          <bdi>{e.currency}</bdi>
          <span dir="auto">{e.name}</span>
          <span>{e.actual ?? e.forecast ?? "—"}</span>
        </div>
      ))}
    </details>
  );
}
