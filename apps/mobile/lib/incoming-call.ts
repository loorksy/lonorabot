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

export type ReachMeChannel = "activity" | "notify" | "message" | "call";

/** The owner's reach-me preference: calls ring only when its channel is "call". */
export type IncomingPolicy = {
  channel: ReachMeChannel;
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

/**
 * The saved form of a reach-me choice. The channel alone decides whether calls ring,
 * so the derived enabled flag is never sent; a call uses the chosen enrolled device,
 * otherwise the most recently enrolled one.
 */
export function reachMePayload(
  policy: IncomingPolicy,
  devices: readonly { id: string }[],
  quiet: { start: string; end: string },
  timezone: string,
): Omit<IncomingPolicy, "enabled"> {
  const hour = (value: string) => {
    const parsed = Number.parseInt(value, 10);
    return value.trim() && Number.isInteger(parsed) && parsed >= 0 && parsed <= 23 ? parsed : null;
  };
  const { enabled: _derived, ...rest } = policy;
  const enrolled = devices.some((device) => device.id === policy.device_id);
  return {
    ...rest,
    device_id: policy.channel === "call" && !enrolled ? (devices[0]?.id ?? null) : policy.device_id,
    quiet_start_hour: hour(quiet.start),
    quiet_end_hour: hour(quiet.end),
    timezone: timezone || policy.timezone,
  };
}
