/** The owner's reach-me policy (`GET/PUT /api/voice/incoming/policy`). Quiet hours are kept
 * in minutes after local midnight (Q47); the whole-hour fields follow them. */
export type IncomingCallPolicy = {
  channel: "activity" | "notify" | "message" | "call";
  enabled: boolean;
  device_id: string | null;
  opportunities: boolean;
  action_required: boolean;
  critical: boolean;
  timezone: string;
  quiet_start_hour: number | null;
  quiet_end_hour: number | null;
  quiet_start_minute: number | null;
  quiet_end_minute: number | null;
  ttl_seconds: number;
  minimum_interval_seconds: number;
};

/** Per-agent delivery rules (`GET/PUT /api/agents/{id}/notifications`, Q47). They only
 * narrow how one agent's own alerts reach the owner; urgent items always show. */
export type AgentDeliveryRules = {
  in_app: boolean;
  calls: boolean;
  daily_limit: number | null;
};
