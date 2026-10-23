/** Push is an untrusted wake hint. Server state always decides whether to ring/join. */
export type IncomingCall = {
  id: string;
  agent_id: string;
  thread_id: string;
  status: "ringing" | "accepted" | "rejected" | "missed" | "cancelled";
  reason: string;
  expires_at: string;
  version: number;
  execution_authorized: false;
};

export type IncomingPolicy = {
  enabled: boolean;
  device_id: string | null;
  opportunities: boolean;
  action_required: boolean;
  critical: boolean;
  timezone: string;
  quiet_start_hour: number | null;
  quiet_end_hour: number | null;
  ttl_seconds: number;
  minimum_interval_seconds: number;
};

export function visibleIncoming(rows: IncomingCall[], now = Date.now()): IncomingCall | null {
  return (
    rows.find(
      (row) =>
        row.status === "ringing" &&
        Number.isFinite(Date.parse(row.expires_at)) &&
        Date.parse(row.expires_at) > now,
    ) ?? null
  );
}

export function acceptedIncoming(row: IncomingCall, now = Date.now()): boolean {
  return (
    row.status === "accepted" &&
    Date.parse(row.expires_at) > now &&
    row.execution_authorized === false
  );
}
